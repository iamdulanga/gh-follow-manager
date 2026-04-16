import os
import time
from typing import Set, List
from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class GitHubFollowerManager:
    """GitHub follower management with verified account protection"""
    
    # Verified accounts that should never be unfollowed
    VERIFIED_PROTECTED = {
        'github', 'microsoft', 'google', 'facebook', 'twitter', 'vercel', 
        'netlify', 'aws', 'cloudflare', 'gitlab', 'stackoverflow', 'npmjs'
    }
    
    def __init__(self):
        self.session = self._create_session()
        self.username = os.getenv('GITHUB_USERNAME')
        self.token = os.getenv('GITHUB_TOKEN')
        
        if not self.username or not self.token:
            raise ValueError("GITHUB_USERNAME and GITHUB_TOKEN required")
        
        self.session.headers.update({
            'Authorization': f'token {self.token}',
            'Accept': 'application/vnd.github.v3+json'
        })
        
        self.exceptions = self._load_exceptions()
    
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
    
    def _paginated_fetch(self, url: str) -> List:
        """Fetch all paginated results"""
        results = []
        while url:
            resp = self.session.get(url)
            if resp.status_code != 200:
                break
            results.extend(resp.json())
            url = resp.links.get('next', {}).get('url')
        return results
    
    def _is_protected(self, username: str) -> bool:
        """Check if account should be protected"""
        username_lower = username.lower()
        return (username_lower in self.VERIFIED_PROTECTED or 
                username_lower in self.exceptions)
    
    def sync_follows(self):
        """Main sync logic"""
        print(f"🔄 Syncing @{self.username}")
        
        # Fetch data
        followers_url = f'https://api.github.com/users/{self.username}/followers?per_page=100'
        following_url = f'https://api.github.com/users/{self.username}/following?per_page=100'
        
        followers = {user['login'].lower() for user in self._paginated_fetch(followers_url)}
        following = {user['login'].lower() for user in self._paginated_fetch(following_url)}
        
        print(f"📊 {len(followers)} followers, {len(following)} following")
        
        # Calculate differences
        not_following_back = following - followers
        not_followed_back = followers - following
        
        # Unfollow non-reciprocal (skip protected)
        unfollowed = []
        for user in not_following_back:
            if self._is_protected(user):
                print(f"🛡️ Skipped protected: {user}")
                continue
            
            resp = self.session.delete(f'https://api.github.com/user/following/{user}')
            if resp.status_code == 204:
                unfollowed.append(user)
                print(f"✓ Unfollowed: {user}")
            time.sleep(0.5)
        
        # Follow back
        followed = []
        for user in not_followed_back:
            resp = self.session.put(f'https://api.github.com/user/following/{user}')
            if resp.status_code == 204:
                followed.append(user)
                print(f"✓ Followed back: {user}")
            time.sleep(0.5)
        
        # Summary
        print("\n" + "="*40)
        print(f"✅ Followed back: {len(followed)}")
        print(f"🗑️ Unfollowed: {len(unfollowed)}")
        print(f"🛡️ Protected: {len(not_following_back) - len(unfollowed)}")
        print("="*40)

def main():
    try:
        manager = GitHubFollowerManager()
        manager.sync_follows()
        return 0
    except Exception as e:
        print(f"❌ Error: {e}")
        return 1

if __name__ == "__main__":
    exit(main())
