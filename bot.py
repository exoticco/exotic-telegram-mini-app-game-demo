"""
🎮 EXOTIC CO MINER BOT - MongoDB Integration
Complete with task tracking and verification
"""

import os
import logging
import json
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)

# MongoDB imports
from pymongo import ASCENDING, DESCENDING
from pymongo.errors import DuplicateKeyError, ConnectionFailure
from bson import ObjectId
import motor.motor_asyncio

# Load environment variables
load_dotenv()

# ==================== CONFIGURATION ====================
BOT_TOKEN = os.getenv('BOT_TOKEN')
BOT_USERNAME = os.getenv('BOT_USERNAME', 'ExoticCoMinerBot')
WEB_APP_URL = os.getenv('WEB_APP_URL', 'https://your-domain.com/game.html')
ADMIN_IDS = [int(x) for x in os.getenv('ADMIN_IDS', '').split(',') if x]

# MongoDB Configuration
MONGODB_URI = os.getenv('MONGODB_URI')
MONGODB_DB_NAME = os.getenv('MONGODB_DB_NAME', 'exoticco_bot')

# Social links
SOCIAL_LINKS = {
    'telegram': 'https://t.me/exoticcoofficial',
    'telegram_group': 'https://t.me/exoticcoofficialchat',
    'twitter': 'https://x.com/ExoticCoDev',
    'instagram': 'https://instagram.com/exoticcoofficial'
}

# Task rewards
TASK_REWARDS = {
    'telegram': 500,
    'telegram_group': 500,
    'twitter': 1000,
    'instagram': 1000,
    'all': 5000
}

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==================== MONGODB DATABASE CLASS ====================
class MongoDB:
    """MongoDB database handler for game data"""
    
    def __init__(self, uri: str, db_name: str):
        """Initialize MongoDB connection"""
        self.client = None
        self.db = None
        self.uri = uri
        self.db_name = db_name
        
        # Collections
        self.users = None
        self.tasks = None
        self.achievements = None
        self.transactions = None
        self.leaderboard_cache = None
        
    async def connect(self):
        """Establish connection to MongoDB"""
        try:
            # Async connection using motor
            self.client = motor.motor_asyncio.AsyncIOMotorClient(self.uri)
            self.db = self.client[self.db_name]
            
            # Initialize collections
            self.users = self.db.users
            self.tasks = self.db.tasks
            self.achievements = self.db.achievements
            self.transactions = self.db.transactions
            self.leaderboard_cache = self.db.leaderboard_cache
            
            # Create indexes
            await self.create_indexes()
            
            logger.info("✅ Connected to MongoDB successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ MongoDB connection failed: {e}")
            return False
    
    async def create_indexes(self):
        """Create necessary indexes for better performance"""
        
        # Users collection indexes
        await self.users.create_index("user_id", unique=True)
        await self.users.create_index("username")
        await self.users.create_index("balance")
        await self.users.create_index("total_clicks")
        await self.users.create_index("last_active")
        
        # Tasks collection indexes
        await self.tasks.create_index([("user_id", ASCENDING), ("task_id", ASCENDING)], unique=True)
        await self.tasks.create_index("completed_at")
        await self.tasks.create_index("claimed_at")
        
        # Transactions collection indexes
        await self.transactions.create_index([("user_id", ASCENDING), ("timestamp", DESCENDING)])
        await self.transactions.create_index("type")
        
        logger.info("✅ MongoDB indexes created")
    
    # ==================== USER MANAGEMENT ====================
    
    async def get_user(self, user_id: int) -> Dict:
        """Get or create user"""
        user = await self.users.find_one({"user_id": user_id})
        
        if not user:
            # Create new user
            user = {
                "user_id": user_id,
                "username": None,
                "first_name": None,
                "last_name": None,
                
                # Game stats
                "balance": 0,
                "click_level": 1,
                "auto_level": 0,
                "crit_level": 0,
                "multi_level": 0,
                "total_clicks": 0,
                "total_earned": 0,
                "games_played": 0,
                
                # Referrals
                "referrals": [],
                "referral_earnings": 0,
                "referred_by": None,
                
                # Settings
                "settings": {
                    "sound_enabled": True,
                    "haptic_enabled": True,
                    "animations_enabled": True,
                    "auto_save": True
                },
                
                # Timestamps
                "joined_at": datetime.utcnow(),
                "last_active": datetime.utcnow(),
                "last_save": datetime.utcnow(),
                
                # Metadata
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            await self.users.insert_one(user)
            logger.info(f"📝 New user created: {user_id}")
        
        return user
    
    async def update_user(self, user_id: int, update_data: Dict) -> bool:
        """Update user data"""
        update_data["updated_at"] = datetime.utcnow()
        
        result = await self.users.update_one(
            {"user_id": user_id},
            {"$set": update_data}
        )
        
        return result.modified_count > 0
    
    async def update_user_stats(self, user_id: int, game_state: Dict):
        """Update user game statistics"""
        user = await self.get_user(user_id)
        
        update_fields = {
            "balance": game_state.get('balance', user.get('balance', 0)),
            "click_level": game_state.get('clickLevel', user.get('click_level', 1)),
            "auto_level": game_state.get('autoLevel', user.get('auto_level', 0)),
            "crit_level": game_state.get('critLevel', user.get('crit_level', 0)),
            "multi_level": game_state.get('multiLevel', user.get('multi_level', 0)),
            "total_clicks": game_state.get('totalClicks', user.get('total_clicks', 0)),
            "total_earned": game_state.get('totalEarned', user.get('total_earned', 0)),
            "games_played": game_state.get('gamesPlayed', user.get('games_played', 0)),
            "last_active": datetime.utcnow()
        }
        
        # Update settings if provided
        if 'settings' in game_state:
            update_fields["settings"] = game_state['settings']
        
        await self.update_user(user_id, update_fields)
        
        # Log transaction
        await self.log_transaction(
            user_id=user_id,
            type="game_update",
            data=game_state
        )
    
    # ==================== TASK MANAGEMENT ====================
    
    async def get_user_tasks(self, user_id: int) -> Dict:
        """Get all tasks for a user"""
        tasks = await self.tasks.find({"user_id": user_id}).to_list(length=None)
        
        # Initialize task structure
        task_status = {
            'telegram': {'completed': False, 'claimed': False},
            'telegram_group': {'completed': False, 'claimed': False},
            'twitter': {'completed': False, 'claimed': False},
            'instagram': {'completed': False, 'claimed': False},
            'all': {'completed': False, 'claimed': False}
        }
        
        # Update with actual data
        for task in tasks:
            task_status[task['task_id']] = {
                'completed': task.get('completed', False),
                'claimed': task.get('claimed', False),
                'completed_at': task.get('completed_at'),
                'claimed_at': task.get('claimed_at'),
                'verified': task.get('verified', False)
            }
        
        return task_status
    
    async def update_task(self, user_id: int, task_id: str, update_data: Dict) -> bool:
        """Update task status"""
        result = await self.tasks.update_one(
            {"user_id": user_id, "task_id": task_id},
            {"$set": update_data, "$setOnInsert": {"created_at": datetime.utcnow()}},
            upsert=True
        )
        
        return result.modified_count > 0 or result.upserted_id is not None
    
    async def complete_task(self, user_id: int, task_id: str) -> Dict:
        """Mark task as completed and give reward"""
        result = {
            'success': False,
            'message': '',
            'reward': 0,
            'task_status': None
        }
        
        # Get current task status
        task = await self.tasks.find_one({"user_id": user_id, "task_id": task_id})
        
        if task and task.get('claimed'):
            result['message'] = 'Task already claimed'
            return result
        
        if task_id == 'all':
            # Check if all other tasks are completed
            other_tasks = ['telegram', 'telegram_group', 'twitter', 'instagram']
            all_completed = True
            
            for t_id in other_tasks:
                t = await self.tasks.find_one({"user_id": user_id, "task_id": t_id})
                if not t or not t.get('claimed'):
                    all_completed = False
                    break
            
            if not all_completed:
                result['message'] = 'Complete all tasks first'
                return result
            
            # Mark all task as completed
            await self.update_task(user_id, 'all', {
                'completed': True,
                'claimed': True,
                'completed_at': datetime.utcnow(),
                'claimed_at': datetime.utcnow()
            })
            
            reward = TASK_REWARDS['all']
            
        else:
            # Regular task
            if not task or not task.get('completed'):
                result['message'] = 'Complete the task first'
                return result
            
            await self.update_task(user_id, task_id, {
                'claimed': True,
                'claimed_at': datetime.utcnow()
            })
            
            reward = TASK_REWARDS.get(task_id, 0)
        
        # Add reward to user balance
        user = await self.get_user(user_id)
        new_balance = user.get('balance', 0) + reward
        
        await self.update_user(user_id, {
            'balance': new_balance,
            'referral_earnings': user.get('referral_earnings', 0) + reward
        })
        
        # Log transaction
        await self.log_transaction(
            user_id=user_id,
            type="task_reward",
            data={
                'task_id': task_id,
                'reward': reward
            }
        )
        
        # Check for all tasks achievement
        await self.check_all_tasks_achievement(user_id)
        
        result['success'] = True
        result['reward'] = reward
        result['message'] = f'Task completed! +{reward} coins'
        
        return result
    
    async def verify_task(self, user_id: int, task_id: str) -> bool:
        """Verify if user completed the task"""
        # In production, implement actual verification
        # This is where you'd check:
        # - Telegram channel membership
        # - Twitter follow
        # - Instagram follow
        
        user = await self.get_user(user_id)
        
        # Example: Telegram verification
        if task_id in ['telegram', 'telegram_group']:
            # Use Telegram Bot API to check membership
            # This would require passing the bot instance
            verified = await self.verify_telegram_membership(user_id, task_id)
        else:
            # For demo, auto-verify
            verified = True
        
        if verified:
            await self.update_task(user_id, task_id, {
                'completed': True,
                'completed_at': datetime.utcnow(),
                'verified': True,
                'verified_at': datetime.utcnow()
            })
            
            # Log verification
            await self.log_transaction(
                user_id=user_id,
                type="task_verification",
                data={'task_id': task_id, 'verified': True}
            )
        
        return verified
    
    async def verify_telegram_membership(self, user_id: int, task_id: str) -> bool:
        """Verify Telegram channel/group membership"""
        # This requires the bot instance to call get_chat_member
        # We'll implement this separately
        return True  # Placeholder
    
    # ==================== ACHIEVEMENTS ====================
    
    async def check_all_tasks_achievement(self, user_id: int):
        """Check if user completed all tasks"""
        tasks = await self.get_user_tasks(user_id)
        
        all_claimed = all(
            tasks[t]['claimed'] 
            for t in ['telegram', 'telegram_group', 'twitter', 'instagram']
        )
        
        if all_claimed:
            # Check if achievement already exists
            achievement = await self.achievements.find_one({
                "user_id": user_id,
                "achievement_id": "social_butterfly"
            })
            
            if not achievement:
                # Give achievement reward
                await self.achievements.insert_one({
                    "user_id": user_id,
                    "achievement_id": "social_butterfly",
                    "name": "Social Butterfly",
                    "description": "Complete all social tasks",
                    "reward": 1000,
                    "unlocked_at": datetime.utcnow()
                })
                
                # Add reward
                user = await self.get_user(user_id)
                await self.update_user(user_id, {
                    'balance': user['balance'] + 1000
                })
                
                logger.info(f"🏆 User {user_id} earned Social Butterfly achievement")
    
    # ==================== REFERRALS ====================
    
    async def add_referral(self, referrer_id: int, referral_id: int) -> bool:
        """Add a referral relationship"""
        referrer = await self.get_user(referrer_id)
        
        if referral_id in referrer.get('referrals', []):
            return False
        
        # Update referrer
        await self.update_user(referrer_id, {
            'referrals': referrer.get('referrals', []) + [referral_id],
            'balance': referrer.get('balance', 0) + 500,
            'referral_earnings': referrer.get('referral_earnings', 0) + 500
        })
        
        # Update referred user
        await self.update_user(referral_id, {
            'referred_by': referrer_id,
            'balance': (await self.get_user(referral_id)).get('balance', 0) + 500
        })
        
        # Log transaction
        await self.log_transaction(
            user_id=referrer_id,
            type="referral_bonus",
            data={'referral_id': referral_id, 'bonus': 500}
        )
        
        return True
    
    # ==================== LEADERBOARD ====================
    
    async def get_leaderboard(self, by: str = 'balance', limit: int = 20) -> List[Dict]:
        """Get leaderboard by different criteria"""
        if by == 'balance':
            cursor = self.users.find({}, {
                'user_id': 1, 'first_name': 1, 'username': 1,
                'balance': 1, 'click_level': 1, 'games_played': 1
            }).sort('balance', DESCENDING).limit(limit)
            
        elif by == 'clicks':
            cursor = self.users.find({}, {
                'user_id': 1, 'first_name': 1, 'username': 1,
                'total_clicks': 1, 'click_level': 1, 'games_played': 1
            }).sort('total_clicks', DESCENDING).limit(limit)
            
        elif by == 'tasks':
            # Aggregate tasks completed
            pipeline = [
                {"$match": {"claimed": True}},
                {"$group": {
                    "_id": "$user_id",
                    "tasks_completed": {"$sum": 1},
                    "total_reward": {"$sum": "$reward"}
                }},
                {"$sort": {"tasks_completed": DESCENDING}},
                {"$limit": limit},
                {"$lookup": {
                    "from": "users",
                    "localField": "_id",
                    "foreignField": "user_id",
                    "as": "user"
                }}
            ]
            
            cursor = await self.tasks.aggregate(pipeline).to_list(length=limit)
            return cursor
        
        leaderboard = await cursor.to_list(length=limit)
        return leaderboard
    
    # ==================== TRANSACTIONS ====================
    
    async def log_transaction(self, user_id: int, type: str, data: Dict):
        """Log user transaction"""
        transaction = {
            "user_id": user_id,
            "type": type,
            "data": data,
            "timestamp": datetime.utcnow()
        }
        
        await self.transactions.insert_one(transaction)
    
    # ==================== STATISTICS ====================
    
    async def get_statistics(self) -> Dict:
        """Get bot statistics"""
        total_users = await self.users.count_documents({})
        active_today = await self.users.count_documents({
            "last_active": {"$gte": datetime.utcnow() - timedelta(days=1)}
        })
        
        # Total coins in economy
        pipeline = [
            {"$group": {
                "_id": None,
                "total_balance": {"$sum": "$balance"},
                "total_earned": {"$sum": "$total_earned"},
                "total_clicks": {"$sum": "$total_clicks"}
            }}
        ]
        
        totals = await self.users.aggregate(pipeline).to_list(length=1)
        totals = totals[0] if totals else {}
        
        # Tasks completed
        tasks_completed = await self.tasks.count_documents({"claimed": True})
        
        return {
            "total_users": total_users,
            "active_today": active_today,
            "total_balance": totals.get("total_balance", 0),
            "total_earned": totals.get("total_earned", 0),
            "total_clicks": totals.get("total_clicks", 0),
            "tasks_completed": tasks_completed
        }
    
    # ==================== ADMIN FUNCTIONS ====================
    
    async def get_user_by_username(self, username: str) -> Optional[Dict]:
        """Find user by username"""
        return await self.users.find_one({"username": username})
    
    async def get_top_referrers(self, limit: int = 10) -> List[Dict]:
        """Get users with most referrals"""
        cursor = self.users.find(
            {"referrals": {"$ne": []}},
            {"user_id": 1, "first_name": 1, "username": 1, "referrals": 1}
        ).sort([("referrals", DESCENDING)]).limit(limit)
        
        return await cursor.to_list(length=limit)
    
    async def get_task_statistics(self) -> Dict:
        """Get task completion statistics"""
        stats = {}
        
        for task_id in TASK_REWARDS.keys():
            completed = await self.tasks.count_documents({
                "task_id": task_id,
                "claimed": True
            })
            stats[task_id] = completed
        
        return stats

# Initialize MongoDB
db = MongoDB(MONGODB_URI, MONGODB_DB_NAME)

# ==================== HELPER FUNCTIONS ====================
def format_number(num: float) -> str:
    """Format large numbers"""
    if num < 1000:
        return str(int(num))
    elif num < 1000000:
        return f"{num/1000:.1f}K"
    elif num < 1000000000:
        return f"{num/1000000:.1f}M"
    else:
        return f"{num/1000000000:.1f}B"

def get_main_menu_keyboard(user_id: int = None):
    """Create main menu keyboard"""
    keyboard = [
        [InlineKeyboardButton("🎮 PLAY GAME", web_app=WebAppInfo(url=WEB_APP_URL))],
        [
            InlineKeyboardButton("👤 Profile", callback_data="profile"),
            InlineKeyboardButton("🏆 Leaderboard", callback_data="leaderboard")
        ],
        [
            InlineKeyboardButton("📋 Tasks", callback_data="tasks"),
            InlineKeyboardButton("⚙️ Settings", callback_data="settings")
        ],
        [InlineKeyboardButton("🤝 Referrals", callback_data="referrals")]
    ]
    
    if user_id and user_id in ADMIN_IDS:
        keyboard.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin")])
    
    return InlineKeyboardMarkup(keyboard)

# ==================== COMMAND HANDLERS ====================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    user = update.effective_user
    user_id = user.id
    
    # Get or create user in MongoDB
    user_data = await db.get_user(user_id)
    
    # Update user info
    await db.update_user(user_id, {
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name
    })
    
    # Check for referral
    if context.args and context.args[0].startswith('ref_'):
        try:
            referrer_id = int(context.args[0].replace('ref_', ''))
            if referrer_id != user_id:
                await db.add_referral(referrer_id, user_id)
                # Notify referrer
                try:
                    await context.bot.send_message(
                        chat_id=referrer_id,
                        text=f"🎉 *New Referral!*\n\n{user.first_name} joined using your link!\nYou earned +500 coins!",
                        parse_mode='Markdown'
                    )
                except:
                    pass
        except:
            pass
    
    welcome_text = f"""
🎮 *Welcome to EXOTIC CO MINER, {user.first_name}!*

🚀 *The Ultimate Crypto Mining Game*

*📋 Social Tasks Available:*
• 📢 Join Telegram Channel (+500)
• 💬 Join Telegram Group (+500)
• 🐦 Follow on Twitter (+1000)
• 📸 Follow on Instagram (+1000)
• 🌟 Complete All (+5000 BONUS)

Click PLAY GAME to start mining!
    """
    
    await update.message.reply_text(
        welcome_text,
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard(user_id)
    )

async def tasks_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show tasks status"""
    user_id = update.effective_user.id
    tasks = await db.get_user_tasks(user_id)
    
    text = "📋 *SOCIAL TASKS*\n\n"
    
    task_details = {
        'telegram': {'emoji': '📢', 'name': 'Telegram Channel', 'link': '@exoticcoofficial', 'reward': 500},
        'telegram_group': {'emoji': '💬', 'name': 'Telegram Group', 'link': '@exoticcoofficialchat', 'reward': 500},
        'twitter': {'emoji': '🐦', 'name': 'Twitter/X', 'link': '@ExoticCoDev', 'reward': 1000},
        'instagram': {'emoji': '📸', 'name': 'Instagram', 'link': '@exoticcoofficial', 'reward': 1000}
    }
    
    for task_id, details in task_details.items():
        task = tasks.get(task_id, {})
        status = "✅ CLAIMED" if task.get('claimed') else "⏳ READY" if task.get('completed') else "🔒 LOCKED"
        
        text += f"{details['emoji']} *{details['name']}*\n"
        text += f"   • Link: {details['link']}\n"
        text += f"   • Reward: +{details['reward']} coins\n"
        text += f"   • Status: {status}\n\n"
    
    # All tasks bonus
    all_task = tasks.get('all', {})
    all_status = "✅ CLAIMED" if all_task.get('claimed') else "🎯 AVAILABLE" if all_task.get('completed') else "🔒 LOCKED"
    
    text += f"🌟 *BONUS: Complete All Tasks*\n"
    text += f"   • Reward: +5000 coins\n"
    text += f"   • Status: {all_status}\n\n"
    
    # Task progress
    completed = sum(1 for t in tasks.values() if t.get('claimed', False))
    text += f"📊 *Progress: {completed}/5 tasks completed*\n"
    
    keyboard = [
        [InlineKeyboardButton("🔄 Refresh", callback_data="refresh_tasks")],
        [InlineKeyboardButton("🔙 Back", callback_data="menu")]
    ]
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def profile_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user profile"""
    user_id = update.effective_user.id
    user = await db.get_user(user_id)
    tasks = await db.get_user_tasks(user_id)
    
    tasks_completed = sum(1 for t in tasks.values() if t.get('claimed', False))
    
    text = f"""
👤 *PROFILE - {user.get('first_name', 'Player')}*

💰 *Balance:* `{format_number(user['balance'])}`
📊 *Level:* `{user['click_level'] + user['auto_level'] + user['crit_level'] + user['multi_level']}`
🎮 *Games Played:* `{user['games_played']}`

📋 *Tasks Completed:* `{tasks_completed}/5`
🤝 *Referrals:* `{len(user.get('referrals', []))}`

📈 *Lifetime Stats:*
• Total Clicks: `{format_number(user['total_clicks'])}`
• Total Earned: `{format_number(user['total_earned'])}`
    """
    
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="menu")]]
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def leaderboard_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show leaderboard"""
    query = update.callback_query if hasattr(update, 'callback_query') else None
    
    if query and query.data and query.data.startswith('leaderboard_'):
        by = query.data.replace('leaderboard_', '')
    else:
        by = 'balance'
    
    users = await db.get_leaderboard(by, 10)
    
    if by == 'balance':
        title = "💰 BALANCE LEADERBOARD"
    elif by == 'clicks':
        title = "🖱️ CLICKS LEADERBOARD"
    else:
        title = "📋 TASKS LEADERBOARD"
    
    text = f"🏆 *{title}*\n\n"
    
    for i, user in enumerate(users, 1):
        name = user.get('first_name') or user.get('username') or f"Player_{user['user_id']}"
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        
        if by == 'balance':
            value = f"💰 {format_number(user['balance'])}"
        elif by == 'clicks':
            value = f"🖱️ {format_number(user['total_clicks'])}"
        else:
            # For tasks leaderboard
            tasks_count = user.get('tasks_completed', 0)
            value = f"📋 {tasks_count} tasks"
        
        text += f"{medal} *{name}*\n"
        text += f"   {value}\n\n"
    
    keyboard = [
        [
            InlineKeyboardButton("💰 Balance", callback_data="leaderboard_balance"),
            InlineKeyboardButton("🖱️ Clicks", callback_data="leaderboard_clicks"),
            InlineKeyboardButton("📋 Tasks", callback_data="leaderboard_tasks")
        ],
        [InlineKeyboardButton("🔙 Back", callback_data="menu")]
    ]
    
    if query:
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to view statistics"""
    user_id = update.effective_user.id
    
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("❌ Access denied")
        return
    
    stats = await db.get_statistics()
    task_stats = await db.get_task_statistics()
    
    text = f"""
⚙️ *Bot Statistics*

📊 *Users:*
• Total: {stats['total_users']}
• Active Today: {stats['active_today']}

💰 *Economy:*
• Total Balance: {format_number(stats['total_balance'])}
• Total Earned: {format_number(stats['total_earned'])}
• Total Clicks: {format_number(stats['total_clicks'])}

📋 *Tasks:*
• Total Completed: {stats['tasks_completed']}
• Telegram Channel: {task_stats.get('telegram', 0)}
• Telegram Group: {task_stats.get('telegram_group', 0)}
• Twitter: {task_stats.get('twitter', 0)}
• Instagram: {task_stats.get('instagram', 0)}
• All Tasks Bonus: {task_stats.get('all', 0)}
    """
    
    await update.message.reply_text(text, parse_mode='Markdown')

# ==================== WEBAPP DATA HANDLER ====================
async def web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle data from web app"""
    user_id = update.effective_user.id
    data = json.loads(update.effective_message.web_app_data.data)
    
    logger.info(f"WebApp data from user {user_id}: {data.get('type', 'unknown')}")
    
    data_type = data.get('type')
    
    if data_type == 'save' and 'state' in data:
        # Update game state in MongoDB
        await db.update_user_stats(user_id, data['state'])
        
        await update.message.reply_text(
            "✅ Game saved successfully!",
            reply_markup=get_main_menu_keyboard(user_id)
        )
    
    elif data_type == 'task_completed':
        # Task completed in game
        task_id = data.get('task')
        if task_id:
            result = await db.complete_task(user_id, task_id)
            
            if result['success']:
                await update.message.reply_text(
                    f"✅ {result['message']}",
                    reply_markup=get_main_menu_keyboard(user_id)
                )
            else:
                await update.message.reply_text(
                    f"❌ {result['message']}",
                    reply_markup=get_main_menu_keyboard(user_id)
                )
    
    elif data_type == 'verify_task':
        # Verify task completion
        task_id = data.get('task')
        if task_id:
            verified = await db.verify_task(user_id, task_id)
            
            if verified:
                await update.message.reply_text(
                    f"✅ Task verified! You can now claim your reward.",
                    reply_markup=get_main_menu_keyboard(user_id)
                )
            else:
                await update.message.reply_text(
                    f"❌ Verification failed. Please make sure you've completed the task.",
                    reply_markup=get_main_menu_keyboard(user_id)
                )

# ==================== CALLBACK HANDLERS ====================
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button callbacks"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = update.effective_user.id
    
    if data == "menu":
        await query.edit_message_text(
            "🎮 *Main Menu*\n\nChoose an option:",
            parse_mode='Markdown',
            reply_markup=get_main_menu_keyboard(user_id)
        )
    
    elif data == "profile":
        await profile_command(update, context)
    
    elif data.startswith("leaderboard"):
        await leaderboard_command(update, context)
    
    elif data == "tasks" or data == "refresh_tasks":
        await tasks_command(update, context)
    
    elif data == "settings":
        settings_text = """
⚙️ *Settings*

Configure in the web app:
• Sound Effects
• Haptic Feedback
• Animations
• Auto-save

Click PLAY GAME to access settings.
        """
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="menu")]]
        await query.edit_message_text(
            settings_text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data == "referrals":
        user = await db.get_user(user_id)
        referral_link = f"https://t.me/{BOT_USERNAME.replace('@', '')}?start=ref_{user_id}"
        
        text = f"""
🤝 *Referral Program*

🔗 *Your Link:*
`{referral_link}`

📊 *Your Stats:*
• Total Referrals: {len(user.get('referrals', []))}
• Earnings: {format_number(user.get('referral_earnings', 0))}

🎁 *Rewards:* 500 coins per referral
        """
        
        keyboard = [
            [InlineKeyboardButton("📋 Copy Link", callback_data="copy_link")],
            [InlineKeyboardButton("🔙 Back", callback_data="menu")]
        ]
        
        await query.edit_message_text(
            text,
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    elif data == "copy_link":
        referral_link = f"https://t.me/{BOT_USERNAME.replace('@', '')}?start=ref_{user_id}"
        await query.message.reply_text(
            f"📋 *Your Referral Link:*\n`{referral_link}`",
            parse_mode='Markdown'
        )

# ==================== MAIN FUNCTION ====================
async def main():
    """Start the bot"""
    print("=" * 50)
    print("🎮 EXOTIC CO MINER BOT - Starting...")
    print("=" * 50)

    if not BOT_TOKEN:
        print("❌ ERROR: Please set your BOT_TOKEN in the .env file!")
        return

    # Connect to MongoDB
    connected = await db.connect()
    if not connected:
        print("❌ ERROR: Failed to connect to MongoDB!")
        return

    # Create bot
    application = Application.builder().token(BOT_TOKEN).build()

    # Command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("profile", profile_command))
    application.add_handler(CommandHandler("leaderboard", leaderboard_command))
    application.add_handler(CommandHandler("tasks", tasks_command))
    application.add_handler(CommandHandler("stats", admin_stats))

    # Buttons
    application.add_handler(CallbackQueryHandler(button_callback))

    # WebApp handler
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, web_app_data))

    # Initialize the application
    await application.initialize()

    # Print bot info
    print(f"\n✅ Bot is running!")
    print(f"📱 Bot: @{BOT_USERNAME}")
    print(f"🗄️  MongoDB: Connected to {MONGODB_DB_NAME}")
    print(f"\n⏰ Press Ctrl+C to stop\n")
    print("=" * 50)

    # Start bot
    await application.start()
    
    # Start polling
    await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)

    # Keep the bot running
    try:
        # Keep the task running
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        # Handle shutdown gracefully
        pass
    finally:
        # Clean shutdown
        await application.updater.stop()
        await application.stop()
        await application.shutdown()

if __name__ == "__main__":
    try:
        # Create and set event loop
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        # Run the main coroutine
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("\n\n👋 Bot stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
    finally:
        # Clean up
        try:
            # Cancel all tasks
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            
            # Run loop until tasks are done
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            
            # Close the loop
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()
        except:
            pass