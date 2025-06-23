# --- START OF FILE database_manager.py ---

import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import logging
import random
from dotenv import load_dotenv
load_dotenv()

# Try to import Supabase, but fallback to mock implementation if not available
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False
    print("Supabase package not available, using mock database")

logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, url: str = None, key: str = None):
        """Initialize Supabase client or mock database"""
        self.url = url or os.getenv("SUPABASE_URL")
        self.key = key or os.getenv("SUPABASE_KEY")
        
        # Store mock data if Supabase isn't available
        self.mock_tickets = []
        
        if SUPABASE_AVAILABLE:
            try:
                self.supabase: Client = create_client(self.url, self.key)
                logger.info("✅ Supabase client initialized successfully")
            except Exception as e:
                logger.error(f"❌ Failed to initialize Supabase client: {e}")
                self._generate_mock_data()
        else:
            self._generate_mock_data()
    
    def _generate_mock_data(self):
        """Generate mock data for demonstration"""
        logger.info("📝 Generating mock data for demo")
        
        categories = ["Technical Issue", "Billing", "Feature Request", "Account", "General"]
        priorities = ["High", "Medium", "Low"]
        sentiments = ["Positive", "Neutral", "Negative"]
        statuses = ["open", "resolved", "forwarded"]
        usernames = ["user123", "customer456", "client789", "member101", "guest202"]
        
        # Create 30 mock tickets
        for i in range(30):
            days_ago = random.randint(0, 30)
            timestamp = datetime.now() - timedelta(days=days_ago)
            ticket = {
                "id": f"TK-{1000 + i}", "user_id": random.randint(100, 999), "username": random.choice(usernames),
                "issue": f"Sample issue #{i+1}", "summary": f"This is a sample ticket summary for demonstration purposes #{i+1}",
                "category": random.choice(categories), "priority": random.choice(priorities), "sentiment": random.choice(sentiments),
                "status": random.choice(statuses), "created_at": timestamp.isoformat()
            }
            self.mock_tickets.append(ticket)
        
        self.mock_tickets.sort(key=lambda x: x["created_at"], reverse=True)

    def create_ticket(self, user_id: int, username: str, issue: str, 
                     summary: str, category: str, priority: str, sentiment: str) -> str:
        """Create a new ticket in Supabase or mock database"""
        try:
            ticket_id = f"TK-{int(datetime.now().timestamp())}"
            ticket_data = {
                "id": ticket_id, "user_id": user_id, "username": username, "issue": issue, "summary": summary,
                "category": category, "priority": priority, "sentiment": sentiment, "status": "open", "created_at": datetime.now().isoformat()
            }
            if SUPABASE_AVAILABLE:
                result = self.supabase.table("tickets").insert(ticket_data).execute()
                if result.data:
                    logger.info(f"✅ Ticket {ticket_id} created successfully")
                    return ticket_id
                else:
                    logger.error("❌ Failed to create ticket - no data returned")
                    return None
            else:
                self.mock_tickets.insert(0, ticket_data)
                logger.info(f"✅ Ticket {ticket_id} created in mock database")
                return ticket_id
        except Exception as e:
            logger.error(f"❌ Error creating ticket: {e}")
            return None

    def get_ticket(self, ticket_id: str) -> Optional[Dict]:
        """Get a specific ticket by ID"""
        try:
            if SUPABASE_AVAILABLE:
                result = self.supabase.table("tickets").select("*").eq("id", ticket_id).execute()
                return result.data[0] if result.data else None
            else:
                return next((ticket for ticket in self.mock_tickets if ticket["id"] == ticket_id), None)
        except Exception as e:
            logger.error(f"❌ Error fetching ticket {ticket_id}: {e}")
            return None

    def update_ticket_status(self, ticket_id: str, status: str, resolution: str = None) -> bool:
        """Update ticket status and resolution"""
        try:
            update_data = {"status": status}
            if resolution:
                update_data["resolution"] = resolution
            if SUPABASE_AVAILABLE:
                result = self.supabase.table("tickets").update(update_data).eq("id", ticket_id).execute()
                if result.data:
                    logger.info(f"✅ Ticket {ticket_id} updated to {status}")
                    return True
                return False
            else:
                for ticket in self.mock_tickets:
                    if ticket["id"] == ticket_id:
                        ticket.update(update_data)
                        logger.info(f"✅ Ticket {ticket_id} updated to {status} in mock database")
                        return True
                return False
        except Exception as e:
            logger.error(f"❌ Error updating ticket {ticket_id}: {e}")
            return False

    def get_user_tickets(self, user_id: int, limit: int = 10) -> List[Dict]:
        """Get all tickets for a specific user"""
        try:
            if SUPABASE_AVAILABLE:
                result = self.supabase.table("tickets").select("*").eq("user_id", user_id).order("created_at", desc=True).limit(limit).execute()
                return result.data if result.data else []
            else:
                return [t for t in self.mock_tickets if t["user_id"] == user_id][:limit]
        except Exception as e:
            logger.error(f"❌ Error fetching user tickets: {e}")
            return []

    def get_all_tickets(self, status: str = None, limit: int = 100) -> List[Dict]:
        """Get all tickets, optionally filtered by status"""
        try:
            if SUPABASE_AVAILABLE:
                query = self.supabase.table("tickets").select("*")
                if status: query = query.eq("status", status)
                result = query.order("created_at", desc=True).limit(limit).execute()
                return result.data if result.data else []
            else:
                filtered = self.mock_tickets
                if status: filtered = [t for t in filtered if t["status"] == status]
                return filtered[:limit]
        except Exception as e:
            logger.error(f"❌ Error fetching all tickets: {e}")
            return []

    def get_ticket_stats(self) -> Dict:
        """Get ticket statistics for dashboard"""
        stats = {"total": 0, "open": 0, "resolved": 0, "forwarded": 0}
        try:
            all_tickets = self.get_all_tickets(limit=10000) # Get all for accurate stats
            stats["total"] = len(all_tickets)
            for ticket in all_tickets:
                if ticket.get("status") in stats:
                    stats[ticket["status"]] += 1
            return stats
        except Exception as e:
            logger.error(f"❌ Error fetching ticket stats: {e}")
            return stats

    def get_category_distribution(self) -> Dict:
        """Get ticket distribution by category"""
        categories = {}
        try:
            all_tickets = self.get_all_tickets(limit=10000)
            for ticket in all_tickets:
                category = ticket.get("category", "Unknown")
                categories[category] = categories.get(category, 0) + 1
            return categories
        except Exception as e:
            logger.error(f"❌ Error fetching category distribution: {e}")
            return {}

    def get_priority_distribution(self) -> Dict:
        """Get ticket distribution by priority"""
        priorities = {}
        try:
            all_tickets = self.get_all_tickets(limit=10000)
            for ticket in all_tickets:
                priority = ticket.get("priority", "Medium")
                priorities[priority] = priorities.get(priority, 0) + 1
            return priorities
        except Exception as e:
            logger.error(f"❌ Error fetching priority distribution: {e}")
            return {}

    def search_tickets(self, search_term: str, limit: int = 50) -> List[Dict]:
        """Search tickets by content"""
        try:
            if SUPABASE_AVAILABLE:
                result = self.supabase.table("tickets").select("*").or_(f"issue.ilike.%{search_term}%,summary.ilike.%{search_term}%,id.ilike.%{search_term}%").order("created_at", desc=True).limit(limit).execute()
                return result.data if result.data else []
            else:
                search_term = search_term.lower()
                return [t for t in self.mock_tickets if search_term in t.get("issue", "").lower() or search_term in t.get("summary", "").lower() or search_term in t.get("id", "").lower()][:limit]
        except Exception as e:
            logger.error(f"❌ Error searching tickets: {e}")
            return []

    def get_tickets_by_date_range(self, start_date: str, end_date: str) -> List[Dict]:
        """Get tickets within a date range"""
        try:
            if SUPABASE_AVAILABLE:
                result = self.supabase.table("tickets").select("*").gte("created_at", start_date).lte("created_at", end_date).order("created_at", desc=True).execute()
                return result.data if result.data else []
            else:
                start, end = datetime.fromisoformat(start_date.replace('Z', '+00:00')), datetime.fromisoformat(end_date.replace('Z', '+00:00'))
                return [t for t in self.mock_tickets if start <= datetime.fromisoformat(t.get("created_at", "").replace('Z', '+00:00')) <= end]
        except Exception as e:
            logger.error(f"❌ Error fetching tickets by date range: {e}")
            return []

    def assign_ticket(self, ticket_id: str, assigned_to: str) -> bool:
        """Assign ticket to an agent"""
        return self.update_ticket_status(ticket_id, self.get_ticket(ticket_id)['status'], resolution=self.get_ticket(ticket_id).get('resolution'))

    def get_recent_activity(self, limit: int = 20) -> List[Dict]:
        """Get recent ticket activity"""
        try:
            if SUPABASE_AVAILABLE:
                result = self.supabase.table("tickets").select("id, status, priority, category, created_at, username").order("created_at", desc=True).limit(limit).execute()
                return result.data if result.data else []
            else:
                return [{k: t.get(k) for k in ["id", "status", "priority", "category", "created_at", "username"]} for t in self.mock_tickets[:limit]]
        except Exception as e:
            logger.error(f"❌ Error fetching recent activity: {e}")
            return []

    # --- NEW METHOD 1: For Root Cause Analysis Dropdown ---
    def get_all_categories(self) -> List[str]:
        """Get a list of all unique ticket categories."""
        try:
            all_tickets = self.get_all_tickets(limit=10000)
            return sorted(list(set(t['category'] for t in all_tickets if 'category' in t)))
        except Exception as e:
            logger.error(f"❌ Error fetching unique categories: {e}")
            return []

    # --- NEW METHOD 2: For fetching data for Root Cause Analysis ---
    def get_summaries_by_category(self, category: str, limit: int = 50) -> List[str]:
        """Get all ticket summaries for a specific category."""
        try:
            if SUPABASE_AVAILABLE:
                result = (self.supabase.table("tickets")
                         .select("summary")
                         .eq("category", category)
                         .order("created_at", desc=True)
                         .limit(limit)
                         .execute())
                return [t['summary'] for t in result.data] if result.data else []
            else:
                return [t['summary'] for t in self.mock_tickets if t.get('category') == category][:limit]
        except Exception as e:
            logger.error(f"❌ Error fetching summaries by category: {e}")
            return []

# Create global instance
db_manager = DatabaseManager()
# --- END OF FILE database_manager.py ---