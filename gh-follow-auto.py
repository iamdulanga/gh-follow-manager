import os
import time
from typing import Set, List, Dict
from dataclasses import dataclass
from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

@dataclass
class FollowStats:
    followed: List[str]
    unfollowed: List[str]
    protected_verified: List[str]

class GitHubFollowerManager:
    """Professional GitHub follower management with verified account protection"""
    
    VERIFIED_PROTECTED = {'github', 'microsoft', 'google', 'facebook', 'twitter', 'vercel', 'netlify'}
    
    def __init__(self):
        self.session = self._create_session()
        self.username = os.getenv('GITHUB_USERNAME')
        self.token = os.getenv('GITHUB_TOKEN')
        
        if not self.username or not self.token:
            raise ValueError("GITHUB_USERNAME and GITHUB_TOKEN environment variables required")
        
        self.session.headers.update({
            'Authorization': f'token {self.token}',
            'Accept': 'application/vnd.github.v3+json'
        })
        
        self.exceptions = self._load_exceptions()
        self.verified_accounts = self._fetch_verified_status()
    
    def _create_session(self) -> Session:
        """Create optimized session with retry strategy"""
        session = Session()
        retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=20)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        return session
    
    def _load_exceptions(self) -> Set[str]:
        """Load exception list from file"""
        if not os.path.exists("exceptions.txt"):
            return set()
        with open("exceptions.txt", "r") as f:
            return {line.strip().lower() for line in f if line.strip()}
    
    def _fetch_verified_status(self) -> Set[str]:
        """Fetch verified status for protected accounts"""
        verified = set()
        for user in self.VERIFIED_PROTECTED:
            try:
                resp = self.session.get(f'https://api.github.com/users/{user}')
                if resp.status_code == 200 and resp.json().get('site_admin', False):
                    verified.add(user.lower())
            except:
                pass
        return verified
    
    def _paginated_fetch(self, url: str) -> List[Dict]:
        """Efficient pagination using generator pattern"""
        results = []
        while url:
            resp = self.session.get(url)
            if resp.status_code != 200:
                break
            results.extend(resp.json())
            url = resp.links.get('next', {}).get('url')
        return results
    
    def _is_verified(self, username: str) -> bool:
        """Check if account is verified (including fetched status)"""
        username_lower = username.lower()
        return (username_lower in self.VERIFIED_PROTECTED or 
                username_lower in self.verified_accounts or
                username_lower in self.exceptions)
    
    def _get_user_follows(self, follow_type: str) -> Set[str]:
        """Fetch followers or following efficiently"""
        url = f'https://api.github.com/users/{self.username}/{follow_type}'
        users = self._paginated_fetch(url)
        return {user['login'].lower() for user in users}
    
    def sync_follows(self) -> FollowStats:
        """Main sync logic with verified account protection"""
        # Fetch data
        followers = self._get_user_follows('followers')
        following = self._get_user_follows('following')
        
        # Calculate differences
        not_following_back = following - followers  # I follow, they don't
        not_followed_back = followers - following   # They follow, I don't
        
        stats = FollowStats(followed=[], unfollowed=[], protected_verified=[])
        
        # Unfollow non-reciprocal accounts (excluding verified/exceptions)
        for user in not_following_back:
            if self._is_verified(user):
                stats.protected_verified.append(f"{user} (verified/protected)")
                continue
            
            resp = self.session.delete(f'https://api.github.com/user/following/{user}')
            if resp.status_code == 204:
                stats.unfollowed.append(user)
                print(f"✓ Unfollowed: {user}")
            else:
                print(f"✗ Failed to unfollow: {user}")
            time.sleep(0.5)  # Rate limit protection
        
        # Follow back missing accounts
        for user in not_followed_back:
            if self._is_verified(user):
                stats.protected_verified.append(f"{user} (verified - skipped follow)")
                continue
                
            resp = self.session.put(f'https://api.github.com/user/following/{user}')
            if resp.status_code == 204:
                stats.followed.append(user)
                print(f"✓ Followed back: {user}")
            else:
                print(f"✗ Failed to follow: {user}")
            time.sleep(0.5)
        
        return stats
    
    def display_report(self, stats: FollowStats):
        """Generate comprehensive report"""
        print("\n" + "="*50)
        print("FOLLOW SYNC REPORT")
        print("="*50)
        
        print(f"\n📊 Newly Followed Back: {len(stats.followed)}")
        if stats.followed:
            for user in stats.followed:
                print(f"  → @{user}")
        
        print(f"\n🗑️ Unfollowed (non-reciprocal): {len(stats.unfollowed)}")
        if stats.unfollowed:
            for user in stats.unfollowed:
                print(f"  → @{user}")
        
        print(f"\n🛡️ Protected from unfollow (verified/exceptions): {len(stats.protected_verified)}")
        if stats.protected_verified:
            for user in stats.protected_verified:
                print(f"  → @{user}")
        
        print("\n" + "="*50)

def main():
    try:
        manager = GitHubFollowerManager()
        print("🔄 Syncing GitHub follows...")
        stats = manager.sync_follows()
        manager.display_report(stats)
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1
    return 0

if __name__ == "__main__":
    exit(main())
