"""
🎮 EXOTIC CO MINER BOT - 24-Hour Mining System
Complete with MongoDB integration and daily mining cycles
"""

import os
import logging
import json
import asyncio
import random
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

# Mining Configuration
SESSION_DURATION_HOURS = 24
BASE_MINING_REWARD = 100
REFERRAL_BONUS_PERCENT = 10
STREAK_BONUSES = {
    7: 500,      # 7-day streak bonus
    30: 2500,    # 30-day streak bonus
    100: 10000   # 100-day streak bonus
}

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
        await self.users.create_index("total_mined")
        await self.users.create_index("current_streak")
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
                
                # Mining stats
                "balance": 0,
                "total_mined": 0,
                "total_sessions": 0,
                "current_streak": 0,
                "best_streak": 0,
                "last_claim_date": None,
                
                # Upgrades
                "mining_level": 1,      # +10% mining rate per level
                "speed_level": 0,       # Reduces mining time by 2% per level
                "boost_level": 0,       # Increases reward by 5% per level
                "crit_level": 0,        # Chance to double reward (5% per level)
                
                # Mining session
                "mining_session": {
                    "is_active": False,
                    "started_at": None,
                    "end_at": None,
                    "claimed_at": None,
                    "base_reward": 0,
                    "final_reward": 0,
                    "boost_applied": False
                },
                
                # Referrals
                "referrals": [],
                "referral_earnings": 0,
                "referred_by": None,
                
                # Settings
                "settings": {
                    "sound_enabled": True,
                    "haptic_enabled": True,
                    "animations_enabled": True,
                    "auto_save": True,
                    "notifications_enabled": True
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
    
    async def update_mining_session(self, user_id: int, session_data: Dict) -> bool:
        """Update mining session data"""
        result = await self.users.update_one(
            {"user_id": user_id},
            {"$set": {"mining_session": session_data, "updated_at": datetime.utcnow()}}
        )
        
        return result.modified_count > 0
    
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
            'total_mined': user.get('total_mined', 0) + reward
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
        
        result['success'] = True
        result['reward'] = reward
        result['message'] = f'Task completed! +{reward} coins'
        
        return result
    
    async def verify_task(self, user_id: int, task_id: str) -> bool:
        """Verify if user completed the task"""
        # In production, implement actual verification
        user = await self.get_user(user_id)
        
        if task_id in ['telegram', 'telegram_group']:
            verified = await self.verify_telegram_membership(user_id, task_id)
        else:
            verified = True
        
        if verified:
            await self.update_task(user_id, task_id, {
                'completed': True,
                'completed_at': datetime.utcnow(),
                'verified': True,
                'verified_at': datetime.utcnow()
            })
            
            await self.log_transaction(
                user_id=user_id,
                type="task_verification",
                data={'task_id': task_id, 'verified': True}
            )
        
        return verified
    
    async def verify_telegram_membership(self, user_id: int, task_id: str) -> bool:
        """Verify Telegram channel/group membership"""
        # Placeholder - implement actual verification
        return True
    
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
                'balance': 1, 'mining_level': 1, 'total_sessions': 1
            }).sort('balance', DESCENDING).limit(limit)
            
        elif by == 'streak':
            cursor = self.users.find({}, {
                'user_id': 1, 'first_name': 1, 'username': 1,
                'current_streak': 1, 'best_streak': 1, 'total_sessions': 1
            }).sort('current_streak', DESCENDING).limit(limit)
            
        elif by == 'mined':
            cursor = self.users.find({}, {
                'user_id': 1, 'first_name': 1, 'username': 1,
                'total_mined': 1, 'mining_level': 1, 'total_sessions': 1
            }).sort('total_mined', DESCENDING).limit(limit)
            
        else:
            cursor = self.users.find({}, {
                'user_id': 1, 'first_name': 1, 'username': 1,
                'balance': 1, 'mining_level': 1, 'total_sessions': 1
            }).sort('balance', DESCENDING).limit(limit)
        
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
                "total_mined": {"$sum": "$total_mined"},
                "total_sessions": {"$sum": "$total_sessions"}
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
            "total_mined": totals.get("total_mined", 0),
            "total_sessions": totals.get("total_sessions", 0),
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

# Initialize MongoDB
db = MongoDB(MONGODB_URI, MONGODB_DB_NAME)

# ==================== MINING SESSION MANAGER ====================
class MiningSessionManager:
    """Handles 24-hour mining sessions"""
    
    SESSION_DURATION = SESSION_DURATION_HOURS * 60 * 60  # seconds
    BASE_REWARD = BASE_MINING_REWARD
    
    def __init__(self, db_instance):
        self.db = db_instance
    
    def format_time(self, seconds: float) -> str:
        """Format seconds into readable time"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds = int(seconds % 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    async def get_mining_status(self, user_id: int) -> Dict:
        """Get current mining status for user"""
        user = await self.db.get_user(user_id)
        mining_session = user.get('mining_session', {})
        
        if not mining_session.get('is_active'):
            return {
                'is_active': False,
                'can_start': True,
                'message': 'No active mining session'
            }
        
        now = datetime.utcnow()
        end_time = mining_session['end_at']
        
        if now >= end_time:
            return {
                'is_active': True,
                'is_ready': True,
                'can_claim': True,
                'base_reward': mining_session['base_reward'],
                'message': 'Mining complete! Ready to claim rewards.'
            }
        
        remaining = (end_time - now).total_seconds()
        return {
            'is_active': True,
            'is_ready': False,
            'remaining_seconds': remaining,
            'remaining_formatted': self.format_time(remaining),
            'end_time': end_time,
            'base_reward': mining_session['base_reward'],
            'message': f'Mining in progress. Time remaining: {self.format_time(remaining)}'
        }
    
    async def start_mining(self, user_id: int) -> Dict:
        """Start a new 24-hour mining session"""
        user = await self.db.get_user(user_id)
        mining_session = user.get('mining_session', {})
        
        # Check if already mining
        if mining_session.get('is_active'):
            if mining_session.get('end_at') > datetime.utcnow():
                remaining = (mining_session['end_at'] - datetime.utcnow()).total_seconds()
                return {
                    'success': False,
                    'message': f'Already mining! Come back in {self.format_time(remaining)}'
                }
        
        # Check if recently claimed
        if mining_session.get('claimed_at'):
            time_since_claim = (datetime.utcnow() - mining_session['claimed_at']).total_seconds()
            if time_since_claim < self.SESSION_DURATION:
                remaining = self.SESSION_DURATION - time_since_claim
                return {
                    'success': False,
                    'message': f'Please wait {self.format_time(remaining)} before starting a new mining session'
                }
        
        # Calculate base reward based on mining level
        base_reward = self.BASE_REWARD * (1 + (user['mining_level'] - 1) * 0.1)
        
        # Add task completion bonus
        tasks = await self.db.get_user_tasks(user_id)
        completed_tasks = sum(1 for t in tasks.values() if t.get('claimed'))
        base_reward += completed_tasks * 50
        
        # Apply speed level (reduces time)
        speed_bonus = 1 - (user['speed_level'] * 0.02)  # Max 40% reduction
        session_duration = self.SESSION_DURATION * max(0.6, speed_bonus)
        
        # Create new session
        now = datetime.utcnow()
        session = {
            'is_active': True,
            'started_at': now,
            'end_at': now + timedelta(seconds=session_duration),
            'claimed_at': None,
            'base_reward': base_reward,
            'final_reward': 0,
            'boost_applied': False
        }
        
        await self.db.update_mining_session(user_id, session)
        
        return {
            'success': True,
            'message': 'Mining started! Come back in 24 hours to claim your rewards.',
            'end_time': session['end_at'],
            'base_reward': base_reward
        }
    
    async def claim_rewards(self, user_id: int, use_boost: bool = False) -> Dict:
        """Claim rewards after 24-hour mining session"""
        user = await self.db.get_user(user_id)
        mining_session = user.get('mining_session', {})
        
        # Validate session
        if not mining_session.get('is_active'):
            return {
                'success': False,
                'message': 'No active mining session. Start mining first!'
            }
        
        now = datetime.utcnow()
        end_time = mining_session['end_at']
        
        # Check if 24 hours have passed
        if now < end_time:
            remaining = (end_time - now).total_seconds()
            return {
                'success': False,
                'message': f'Mining in progress! {self.format_time(remaining)} remaining.'
            }
        
        # Calculate final reward
        base_reward = mining_session['base_reward']
        multiplier = 1.0
        
        # Apply mining level bonus
        multiplier *= (1 + (user['mining_level'] - 1) * 0.1)
        
        # Apply boost level bonus
        multiplier *= (1 + user['boost_level'] * 0.05)
        
        # Apply boost if requested
        boost_used = False
        if use_boost and not mining_session['boost_applied']:
            multiplier *= 2
            mining_session['boost_applied'] = True
            boost_used = True
        
        # Check for critical hit
        crit_chance = min(user['crit_level'] * 0.05, 0.3)
        is_critical = random.random() < crit_chance
        if is_critical:
            multiplier *= 2
        
        final_reward = int(base_reward * multiplier)
        
        # Update streak
        new_streak = await self.update_streak(user_id)
        
        # Give streak bonus if applicable
        streak_bonus = 0
        if new_streak in STREAK_BONUSES:
            streak_bonus = STREAK_BONUSES[new_streak]
            final_reward += streak_bonus
        
        # Update user balance and stats
        new_balance = user['balance'] + final_reward
        
        # Update database
        await self.db.update_user(user_id, {
            'balance': new_balance,
            'total_mined': user['total_mined'] + final_reward,
            'total_sessions': user['total_sessions'] + 1,
            'current_streak': new_streak,
            'best_streak': max(new_streak, user.get('best_streak', 0)),
            'last_claim_date': now,
            'last_active': now
        })
        
        # Mark session as claimed
        mining_session['is_active'] = False
        mining_session['claimed_at'] = now
        mining_session['final_reward'] = final_reward
        await self.db.update_mining_session(user_id, mining_session)
        
        # Process referral rewards
        if user.get('referred_by'):
            await self.give_referral_reward(user['referred_by'], final_reward)
        
        # Log transaction
        await self.db.log_transaction(
            user_id=user_id,
            type="mining_claim",
            data={
                'reward': final_reward,
                'base': base_reward,
                'multiplier': multiplier,
                'streak': new_streak,
                'streak_bonus': streak_bonus,
                'critical': is_critical,
                'boost_used': boost_used
            }
        )
        
        return {
            'success': True,
            'reward': final_reward,
            'base_reward': base_reward,
            'multiplier': multiplier,
            'streak': new_streak,
            'streak_bonus': streak_bonus,
            'is_critical': is_critical,
            'boost_used': boost_used,
            'message': f'✨ You mined {self.format_number(final_reward)} coins!'
        }
    
    async def update_streak(self, user_id: int) -> int:
        """Update daily streak"""
        user = await self.db.get_user(user_id)
        last_claim = user.get('last_claim_date')
        
        if not last_claim:
            return 1
        
        time_diff = (datetime.utcnow() - last_claim).total_seconds()
        grace_period = self.SESSION_DURATION * 1.5  # 36 hours grace period
        
        if time_diff <= grace_period:
            return user.get('current_streak', 0) + 1
        else:
            return 1
    
    async def give_referral_reward(self, referrer_id: int, claimed_reward: int):
        """Give referral reward to referrer"""
        referral_bonus = int(claimed_reward * REFERRAL_BONUS_PERCENT / 100)
        
        referrer = await self.db.get_user(referrer_id)
        
        await self.db.update_user(referrer_id, {
            'balance': referrer['balance'] + referral_bonus,
            'referral_earnings': referrer.get('referral_earnings', 0) + referral_bonus
        })
        
        await self.db.log_transaction(
            user_id=referrer_id,
            type="referral_earning",
            data={'bonus': referral_bonus, 'from_mining': True}
        )
    
    def format_number(self, num: float) -> str:
        """Format large numbers"""
        if num < 1000:
            return str(int(num))
        elif num < 1000000:
            return f"{num/1000:.1f}K"
        elif num < 1000000000:
            return f"{num/1000000:.1f}M"
        else:
            return f"{num/1000000000:.1f}B"

# Initialize mining manager
mining_manager = MiningSessionManager(db)

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
        [InlineKeyboardButton("⛏️ START MINING", callback_data="start_mining")],
        [
            InlineKeyboardButton("📊 Mining Status", callback_data="mining_status"),
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

🚀 *The Ultimate 24-Hour Mining Game*

⛏️ *How it works:*
• Click START MINING to begin a 24-hour mining session
• Return after 24 hours to claim your rewards
• Maintain daily streaks for bonus rewards
• Upgrade your mining equipment to earn more

📋 *Social Tasks Available:*
• 📢 Join Telegram Channel (+500)
• 💬 Join Telegram Group (+500)
• 🐦 Follow on Twitter (+1000)
• 📸 Follow on Instagram (+1000)
• 🌟 Complete All (+5000 BONUS)

🔥 *Streak Bonuses:*
• 7 days: +500 coins
• 30 days: +2500 coins
• 100 days: +10000 coins

Click START MINING to begin your mining journey!
    """
    
    await update.message.reply_text(
        welcome_text,
        parse_mode='Markdown',
        reply_markup=get_main_menu_keyboard(user_id)
    )

async def start_mining_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start mining command"""
    user_id = update.effective_user.id
    
    result = await mining_manager.start_mining(user_id)
    
    if result['success']:
        keyboard = [[InlineKeyboardButton("📊 Check Status", callback_data="mining_status")]]
        await update.message.reply_text(
            f"⛏️ *Mining Started!*\n\n"
            f"{result['message']}\n\n"
            f"💰 *Expected reward:* {format_number(result['base_reward'])} coins\n"
            f"⏰ *Completion time:* {result['end_time'].strftime('%Y-%m-%d %H:%M UTC')}\n\n"
            f"Come back in 24 hours to claim your rewards!",
            parse_mode='Markdown',
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await update.message.reply_text(
            f"❌ {result['message']}",
            parse_mode='Markdown'
        )

async def mining_status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check mining status"""
    user_id = update.effective_user.id
    user = await db.get_user(user_id)
    status = await mining_manager.get_mining_status(user_id)
    
    if status['is_active'] and status.get('is_ready'):
        text = (
            f"✅ *Mining Complete!*\n\n"
            f"Your 24-hour mining session is ready to claim!\n\n"
            f"💰 *Base reward:* {format_number(status['base_reward'])} coins\n"
            f"⚡ *Multiplier:* {1 + (user['mining_level'] - 1) * 0.1 + user['boost_level'] * 0.05:.1f}x\n"
            f"🔥 *Current streak:* {user.get('current_streak', 0)} days\n\n"
            f"Use BOOST to double your reward!"
        )
        keyboard = [
            [InlineKeyboardButton("💰 Claim Rewards", callback_data="claim_rewards")],
            [InlineKeyboardButton("⚡ Use Boost (2x)", callback_data="claim_rewards_boost")]
        ]
    elif status['is_active']:
        text = (
            f"⛏️ *Mining in Progress*\n\n"
            f"⏰ *Time remaining:* {status['remaining_formatted']}\n"
            f"💰 *Expected reward:* {format_number(status['base_reward'])} coins\n"
            f"⚡ *Current multiplier:* {1 + (user['mining_level'] - 1) * 0.1 + user['boost_level'] * 0.05:.1f}x\n"
            f"🔥 *Current streak:* {user.get('current_streak', 0)} days\n\n"
            f"Come back when the timer reaches 00:00:00 to claim!"
        )
        keyboard = [[InlineKeyboardButton("🔄 Refresh", callback_data="mining_status")]]
    else:
        text = (
            f"⛏️ *No Active Mining Session*\n\n"
            f"💰 *Balance:* {format_number(user['balance'])} coins\n"
            f"⚡ *Mining Level:* {user['mining_level']}\n"
            f"🔥 *Best streak:* {user.get('best_streak', 0)} days\n\n"
            f"Start a new 24-hour mining session now!"
        )
        keyboard = [[InlineKeyboardButton("🚀 Start Mining", callback_data="start_mining")]]
    
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

async def claim_rewards_command(update: Update, context: ContextTypes.DEFAULT_TYPE, use_boost: bool = False):
    """Claim rewards"""
    user_id = update.effective_user.id
    
    result = await mining_manager.claim_rewards(user_id, use_boost)
    
    if result['success']:
        text = (
            f"🎉 *Rewards Claimed!*\n\n"
            f"✨ You mined: *{format_number(result['reward'])} coins*\n"
            f"📊 Base reward: {format_number(result['base_reward'])}\n"
            f"⚡ Multiplier: {result['multiplier']:.1f}x\n"
            f"🔥 Current streak: {result['streak']} days\n"
        )
        
        if result.get('streak_bonus'):
            text += f"🎁 Streak bonus: +{format_number(result['streak_bonus'])} coins\n"
        if result.get('is_critical'):
            text += f"✨ *CRITICAL HIT!* ✨\n"
        if result.get('boost_used'):
            text += f"⚡ *BOOST APPLIED!* ⚡\n"
        
        text += f"\n💰 New balance: {format_number((await db.get_user(user_id))['balance'])} coins"
        
        keyboard = [[InlineKeyboardButton("🚀 Start New Mining", callback_data="start_mining")]]
        
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
    else:
        if update.callback_query:
            await update.callback_query.answer(result['message'], show_alert=True)
        else:
            await update.message.reply_text(f"❌ {result['message']}")

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
⛏️ *Total Mined:* `{format_number(user['total_mined'])}`
🎮 *Mining Sessions:* `{user['total_sessions']}`

⚡ *Upgrades:*
• Mining Level: {user['mining_level']} (+{(user['mining_level']-1)*10}%)
• Speed Level: {user['speed_level']} (-{user['speed_level']*2}% time)
• Boost Level: {user['boost_level']} (+{user['boost_level']*5}%)
• Crit Level: {user['crit_level']} ({min(user['crit_level']*5, 30)}% chance)

🔥 *Streaks:*
• Current: {user.get('current_streak', 0)} days
• Best: {user.get('best_streak', 0)} days

📋 *Tasks Completed:* `{tasks_completed}/5`
🤝 *Referrals:* `{len(user.get('referrals', []))}`
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
    elif by == 'streak':
        title = "🔥 STREAK LEADERBOARD"
    elif by == 'mined':
        title = "⛏️ TOTAL MINED LEADERBOARD"
    else:
        title = "💰 BALANCE LEADERBOARD"
    
    text = f"🏆 *{title}*\n\n"
    
    for i, user in enumerate(users, 1):
        name = user.get('first_name') or user.get('username') or f"Player_{user['user_id']}"
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
        
        if by == 'balance':
            value = f"💰 {format_number(user['balance'])}"
        elif by == 'streak':
            value = f"🔥 {user.get('current_streak', 0)} days"
        else:
            value = f"⛏️ {format_number(user.get('total_mined', 0))}"
        
        text += f"{medal} *{name}*\n"
        text += f"   {value}\n\n"
    
    keyboard = [
        [
            InlineKeyboardButton("💰 Balance", callback_data="leaderboard_balance"),
            InlineKeyboardButton("🔥 Streak", callback_data="leaderboard_streak"),
            InlineKeyboardButton("⛏️ Mined", callback_data="leaderboard_mined")
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
    
    text = f"""
⚙️ *Bot Statistics*

📊 *Users:*
• Total: {stats['total_users']}
• Active Today: {stats['active_today']}

💰 *Economy:*
• Total Balance: {format_number(stats['total_balance'])}
• Total Mined: {format_number(stats['total_mined'])}
• Total Sessions: {stats['total_sessions']}

📋 *Tasks Completed:* {stats['tasks_completed']}
    """
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def upgrades_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show upgrades page"""
    user_id = update.effective_user.id
    user = await db.get_user(user_id)
    
    text = f"""
⚡ *MINING UPGRADES*

💰 *Balance:* {format_number(user['balance'])} coins

*Mining Level* (Level {user['mining_level']})
• Cost: {format_number(100 * (1.5 ** (user['mining_level'] - 1)))}
• Effect: +10% mining reward

*Speed Level* (Level {user['speed_level']})
• Cost: {format_number(500 * (1.5 ** user['speed_level']))}
• Effect: -2% mining time

*Boost Level* (Level {user['boost_level']})
• Cost: {format_number(1000 * (1.5 ** user['boost_level']))}
• Effect: +5% all earnings

*Crit Level* (Level {user['crit_level']})
• Cost: {format_number(2000 * (1.5 ** user['crit_level']))}
• Effect: +5% critical chance

Use the web app to upgrade your equipment!
    """
    
    keyboard = [[InlineKeyboardButton("🎮 Open Game", web_app=WebAppInfo(url=WEB_APP_URL))]]
    
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

# ==================== WEBAPP DATA HANDLER ====================
async def web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle data from web app"""
    user_id = update.effective_user.id
    data = json.loads(update.effective_message.web_app_data.data)
    
    logger.info(f"WebApp data from user {user_id}: {data.get('type', 'unknown')}")
    
    data_type = data.get('type')
    
    if data_type == 'get_mining_status':
        status = await mining_manager.get_mining_status(user_id)
        await update.message.reply_text(
            json.dumps(status),
            reply_markup=get_main_menu_keyboard(user_id)
        )
    
    elif data_type == 'start_mining':
        result = await mining_manager.start_mining(user_id)
        await update.message.reply_text(
            json.dumps(result),
            reply_markup=get_main_menu_keyboard(user_id)
        )
    
    elif data_type == 'claim_rewards':
        use_boost = data.get('use_boost', False)
        result = await mining_manager.claim_rewards(user_id, use_boost)
        await update.message.reply_text(
            json.dumps(result),
            reply_markup=get_main_menu_keyboard(user_id)
        )
    
    elif data_type == 'upgrade':
        upgrade_type = data.get('upgrade')
        if upgrade_type:
            result = await buy_upgrade(user_id, upgrade_type)
            await update.message.reply_text(
                json.dumps(result),
                reply_markup=get_main_menu_keyboard(user_id)
            )
    
    elif data_type == 'task_completed':
        task_id = data.get('task')
        if task_id:
            result = await db.complete_task(user_id, task_id)
            await update.message.reply_text(
                json.dumps(result),
                reply_markup=get_main_menu_keyboard(user_id)
            )
    
    elif data_type == 'verify_task':
        task_id = data.get('task')
        if task_id:
            verified = await db.verify_task(user_id, task_id)
            result = {'verified': verified}
            await update.message.reply_text(
                json.dumps(result),
                reply_markup=get_main_menu_keyboard(user_id)
            )
    
    elif data_type == 'save_settings':
        settings = data.get('settings', {})
        await db.update_user(user_id, {'settings': settings})
        await update.message.reply_text(
            '{"success": true, "message": "Settings saved"}',
            reply_markup=get_main_menu_keyboard(user_id)
        )

async def buy_upgrade(user_id: int, upgrade_type: str) -> Dict:
    """Buy upgrade for user"""
    user = await db.get_user(user_id)
    
    upgrade_prices = {
        'mining': 100,
        'speed': 500,
        'boost': 1000,
        'crit': 2000
    }
    
    level_field = f"{upgrade_type}_level"
    current_level = user.get(level_field, 0)
    
    if upgrade_type == 'mining':
        current_level = user.get('mining_level', 1)
        price = int(100 * (1.5 ** (current_level - 1)))
    else:
        price = int(upgrade_prices[upgrade_type] * (1.5 ** current_level))
    
    if user['balance'] >= price:
        new_balance = user['balance'] - price
        
        if upgrade_type == 'mining':
            new_level = current_level + 1
            await db.update_user(user_id, {
                'balance': new_balance,
                'mining_level': new_level
            })
        else:
            new_level = current_level + 1
            await db.update_user(user_id, {
                'balance': new_balance,
                level_field: new_level
            })
        
        await db.log_transaction(
            user_id=user_id,
            type="upgrade",
            data={'upgrade': upgrade_type, 'price': price, 'new_level': new_level}
        )
        
        return {
            'success': True,
            'message': f'{upgrade_type.capitalize()} upgraded to level {new_level}!',
            'new_level': new_level,
            'balance': new_balance
        }
    else:
        return {
            'success': False,
            'message': f'Not enough coins! Need {format_number(price)} coins.'
        }

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
    
    elif data == "start_mining":
        result = await mining_manager.start_mining(user_id)
        if result['success']:
            await query.edit_message_text(
                f"⛏️ *Mining Started!*\n\n"
                f"{result['message']}\n\n"
                f"💰 *Expected reward:* {format_number(result['base_reward'])} coins\n"
                f"⏰ *Completion time:* {result['end_time'].strftime('%Y-%m-%d %H:%M UTC')}",
                parse_mode='Markdown',
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📊 Check Status", callback_data="mining_status")]])
            )
        else:
            await query.edit_message_text(
                f"❌ {result['message']}",
                parse_mode='Markdown',
                reply_markup=get_main_menu_keyboard(user_id)
            )
    
    elif data == "mining_status":
        await mining_status_command(update, context)
    
    elif data == "claim_rewards":
        await claim_rewards_command(update, context, False)
    
    elif data == "claim_rewards_boost":
        await claim_rewards_command(update, context, True)
    
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
• Notifications

Click PLAY GAME to access settings.
        """
        keyboard = [
            [InlineKeyboardButton("🎮 Open Game", web_app=WebAppInfo(url=WEB_APP_URL))],
            [InlineKeyboardButton("🔙 Back", callback_data="menu")]
        ]
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

🎁 *Rewards:* 500 coins per referral + 10% of their mining rewards!
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
    
    elif data == "upgrades":
        await upgrades_command(update, context)

# ==================== MAIN FUNCTION ====================
async def main():
    """Start the bot"""
    print("=" * 50)
    print("🎮 EXOTIC CO MINER BOT - Starting...")
    print("⛏️  24-Hour Mining System")
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
    application.add_handler(CommandHandler("mine", start_mining_command))
    application.add_handler(CommandHandler("status", mining_status_command))
    application.add_handler(CommandHandler("claim", claim_rewards_command))
    application.add_handler(CommandHandler("profile", profile_command))
    application.add_handler(CommandHandler("leaderboard", leaderboard_command))
    application.add_handler(CommandHandler("tasks", tasks_command))
    application.add_handler(CommandHandler("upgrades", upgrades_command))
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
    print(f"⛏️  Mining Duration: {SESSION_DURATION_HOURS} hours")
    print(f"💰 Base Reward: {BASE_MINING_REWARD} coins")
    print(f"\n⏰ Press Ctrl+C to stop\n")
    print("=" * 50)

    # Start bot
    await application.start()
    
    # Start polling
    await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)

    # Keep the bot running
    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()

if __name__ == "__main__":
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("\n\n👋 Bot stopped by user")
    except Exception as e:
        print(f"\n❌ Error: {e}")
    finally:
        try:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.close()
        except:
            pass