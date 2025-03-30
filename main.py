import discord
from discord.ext import commands, tasks
import aiosqlite
import os
import json
import asyncio
from datetime import datetime
import logging
from dotenv import load_dotenv
import random
import string
import sys

# Add the current directory to the Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("shop_bot")

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
ADMIN_ROLE_ID = int(os.getenv('ADMIN_ROLE_ID', 0))
LTC_ADDRESS = os.getenv('LTC_ADDRESS')

# Print token info for debugging (don't log the full token for security)
if TOKEN:
    logger.info(f"Token loaded successfully. First 5 chars: {TOKEN[:5]}...")
    logger.info(f"Token length: {len(TOKEN)}")
else:
    logger.error("TOKEN NOT FOUND IN ENVIRONMENT VARIABLES!")
    logger.info("Environment variables available: " + str([k for k in os.environ.keys()]))
    logger.info("Current directory: " + os.getcwd())
    logger.info("Files in directory: " + str(os.listdir('.')))
    if os.path.exists('.env'):
        logger.info(".env file exists, checking content length")
        with open('.env', 'r') as f:
            env_content = f.read()
            logger.info(f".env file length: {len(env_content)} chars")
    else:
        logger.info(".env file does not exist")

# Bot configuration
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='s!', intents=intents, help_command=None)

# Store LTC address in bot so it can be accessed by cogs
bot.LTC_ADDRESS = LTC_ADDRESS

# Database path
DB_PATH = "shop_database.db"

# Enhanced colors for embeds with a more modern palette
COLORS = {
    "success": 0x43B581,  # Green
    "error": 0xF04747,    # Red
    "info": 0x7289DA,     # Blurple
    "warning": 0xFAA61A,  # Amber
    "shop": 0x36393F,     # Dark gray
    "payment": 0x5865F2,  # Discord blue
    "product": 0x9B59B6,  # Purple
    "admin": 0xE91E63,    # Pink
    "primary": 0x5865F2   # Discord blue
}

# Set bot's colors for easy access in cogs
bot.COLORS = COLORS

# Embed styling functions
def create_embed(title, description, color=COLORS["primary"], timestamp=True):
    """Create a beautifully styled embed with consistent formatting"""
    embed = discord.Embed(
        title=title,
        description=description,
        color=color
    )
    if timestamp:
        embed.timestamp = datetime.now()
    
    # Add subtle footer branding
    embed.set_footer(text="Shop Bot 2.0", icon_url="https://i.imgur.com/1GMKahQ.png")
    return embed

# Make the embed function available to cogs
bot.create_embed = create_embed

# Function to generate confirmation keys
def generate_confirmation_key(length=8):
    """Generate a unique confirmation key for orders"""
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

# Initialize database
async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        # Create items table
        await db.execute('''
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            price REAL,
            stock INTEGER,
            description TEXT,
            drive_link TEXT
        )
        ''')
        
        # Create orders table
        await db.execute('''
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            item_id INTEGER,
            quantity INTEGER,
            total_price REAL,
            ltc_amount REAL,
            status TEXT,
            confirmation_key TEXT,
            payment_confirmed BOOLEAN DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            paid_at TIMESTAMP,
            delivered_at TIMESTAMP,
            FOREIGN KEY (item_id) REFERENCES items (id)
        )
        ''')
        
        # Create banned users table
        await db.execute('''
        CREATE TABLE IF NOT EXISTS banned_users (
            user_id INTEGER PRIMARY KEY,
            banned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reason TEXT
        )
        ''')
        
        # Check for and add missing columns if needed
        # Check for payment_confirmed column in orders
        try:
            await db.execute("SELECT payment_confirmed FROM orders LIMIT 1")
        except aiosqlite.OperationalError:
            logger.info("Adding missing payment_confirmed column to orders table")
            await db.execute("ALTER TABLE orders ADD COLUMN payment_confirmed BOOLEAN DEFAULT 0")
        
        # Check for confirmation_key column in orders
        try:
            await db.execute("SELECT confirmation_key FROM orders LIMIT 1")
        except aiosqlite.OperationalError:
            logger.info("Adding missing confirmation_key column to orders table")
            await db.execute("ALTER TABLE orders ADD COLUMN confirmation_key TEXT")
        
        # Check for drive_link column in items
        try:
            await db.execute("SELECT drive_link FROM items LIMIT 1")
        except aiosqlite.OperationalError:
            logger.info("Adding missing drive_link column to items table")
            await db.execute("ALTER TABLE items ADD COLUMN drive_link TEXT")
        
        await db.commit()
        logger.info("Database initialization complete")

@bot.event
async def on_ready():
    logger.info(f'{bot.user.name} has connected to Discord!')
    await init_db()
    check_payments.start()

# Tasks
@tasks.loop(minutes=2)
async def check_payments():
    """Check for pending payments and update if paid"""
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            async with db.execute(
                "SELECT id, user_id, item_id, total_price FROM orders WHERE status = 'pending' AND payment_confirmed = 0"
            ) as cursor:
                pending_orders = await cursor.fetchall()
        except aiosqlite.OperationalError as e:
            # If we still encounter an error with the column, log it and use a fallback query
            logger.error(f"Error in check_payments: {e}")
            async with db.execute(
                "SELECT id, user_id, item_id, total_price FROM orders WHERE status = 'pending'"
            ) as cursor:
                pending_orders = await cursor.fetchall()
        
        for order in pending_orders:
            order_id, user_id, item_id, total_price = order
            
            # In a real implementation, we would check the blockchain for payments
            # For this simplified version, we'll assume payments are manually confirmed
            
            # Fetch the user and send a reminder
            user = bot.get_user(user_id)
            if user:
                try:
                    payment_reminder = create_embed(
                        "💸 Payment Reminder",
                        f"Hey there! Just a reminder about your pending order.",
                        COLORS["info"]
                    )
                    payment_reminder.add_field(
                        name="Order Details",
                        value=f"**Order ID:** #{order_id}\n**Amount Due:** ${total_price:.2f}",
                        inline=False
                    )
                    payment_reminder.add_field(
                        name="Payment Instructions",
                        value=f"Please send **{total_price} LTC** to:\n`{LTC_ADDRESS}`\n\nAfter sending payment, use `s!confirm <confirmation_key>` to notify us.",
                        inline=False
                    )
                    
                    await user.send(embed=payment_reminder)
                except:
                    pass

@check_payments.before_loop
async def before_check_payments():
    await bot.wait_until_ready()

# Helper functions
async def is_admin(ctx):
    """Check if the user has admin permissions"""
    if not ctx.guild:
        return False
    
    admin_role = discord.utils.get(ctx.guild.roles, id=ADMIN_ROLE_ID)
    if admin_role and admin_role in ctx.author.roles:
        return True
    
    return ctx.author.guild_permissions.administrator

async def is_banned(user_id):
    """Check if a user is banned from using the shop"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM banned_users WHERE user_id = ?", (user_id,)
        ) as cursor:
            return await cursor.fetchone() is not None

# Error handling
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        return
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(
            embed=create_embed(
                "❌ Error: Missing Argument",
                f"You're missing the `{error.param.name}` parameter.\nCheck `s!help` for proper command usage.",
                COLORS["error"]
            )
        )
    elif isinstance(error, commands.BadArgument):
        await ctx.send(
            embed=create_embed(
                "❌ Error: Invalid Argument",
                "One of the values you provided isn't valid.\nCheck `s!help` for proper command usage.",
                COLORS["error"]
            )
        )
    elif isinstance(error, commands.CheckFailure):
        await ctx.send(
            embed=create_embed(
                "🔒 Access Denied",
                "You don't have permission to use this command.",
                COLORS["error"]
            )
        )
    else:
        logger.error(f"Unhandled error: {error}")
        await ctx.send(
            embed=create_embed(
                "⚠️ Something Went Wrong",
                "An unexpected error occurred. Please try again later.",
                COLORS["error"]
            )
        )

# Load cogs
async def load_extensions():
    try:
        # Check if cogs directory exists
        if not os.path.exists('./cogs'):
            logger.error("Cogs directory not found!")
            logger.info(f"Current directory: {os.getcwd()}")
            logger.info(f"Directory contents: {os.listdir('.')}")
            
            # Try to find cogs in different locations
            possible_locations = ['./cogs', '/opt/render/project/src/cogs', '../cogs', '../../cogs']
            cogs_dir = None
            
            for loc in possible_locations:
                if os.path.exists(loc):
                    logger.info(f"Found cogs directory at: {loc}")
                    cogs_dir = loc
                    break
            
            if not cogs_dir:
                logger.error("Could not find cogs directory in any location!")
                return
        else:
            cogs_dir = './cogs'
            
        # Load the cogs from the found directory
        for filename in os.listdir(cogs_dir):
            if filename.endswith('.py'):
                await bot.load_extension(f'cogs.{filename[:-3]}')
                logger.info(f"Loaded extension: {filename}")
    except Exception as e:
        logger.error(f"Error loading extensions: {e}")

# Run the bot
async def main():
    async with bot:
        await load_extensions()
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main()) 