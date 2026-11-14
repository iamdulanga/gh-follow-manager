import os
import re
import time
from datetime import datetime, timezone
from typing import Set, List, Dict, Optional
from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# ─────────────────────────────────────────────
#  Spam / Bot Detection Heuristics
# ─────────────────────────────────────────────
SPAM_BIO_KEYWORDS = re.compile(
    r'crypto|bitcoin|nft|forex|trading|invest|profit|earn money|onlyfans|adult|'
    r'escort|porn|xxx|casino|bet|gambling|click here|follow back|followback|'
    r'instagram follower|tiktok follower|youtube subscriber|cheap|discount|promo',
    re.IGNORECASE
)

SPAM_LINK_PATTERNS = re.compile(
    r'bit\.ly|tinyurl|t\.co|goo\.gl|ow\.ly|rb\.gy|cutt\.ly|'
    r'telegram\.me|t\.me|wa\.me|discord\.gg',
    re.IGNORECASE
)

# Username patterns typical of bot/spam account generators
_REPEATED_CHARS   = re.compile(r'(.)\1{3,}')                         # 4+ same char: mmmm, pppp
_BOT_NAME_PATTERN = re.compile(r'^[a-z]{3,10}[a-z]{3,10}\d{0,6}$')  # firstname+lastname±digits
_LEETSPEAK_HEAVY  = re.compile(r'(?:[0-9][a-z]|[a-z][0-9]){3,}')    # alternating letter/digit: a1b2c3
_NAME_DIGITS      = re.compile(r'^[a-z]{3,}\d{4,}$')                 # name + 4+ digits: john1234


def _username_is_suspicious(login: str) -> tuple[bool, str]:
    lo = login.lower()
    if _REPEATED_CHARS.search(lo):
        return True, f"repeated chars in username ('{login}')"
    if _LEETSPEAK_HEAVY.search(lo):
        return True, f"heavy leetspeak username ('{login}')"
    if _NAME_DIGITS.match(lo):
        return True, f"name+digits username ('{login}')"
    if _BOT_NAME_PATTERN.match(lo) and len(lo) >= 10:
        return True, f"bot name-pattern username ('{login}')"
    return False, ""


def is_spam_account(profile: dict, min_account_age_days: int = 30) -> tuple[bool, str]:
    """
    Analyse a GitHub user profile dict and return (is_spam, reason).
    Scoring:
      • 1 STRONG signal  → spam  (bio keyword, suspicious link, obvious username + hollow/ratio)
      • 2+ weak signals  → spam
      • 1 weak + suspicious username → spam
    """
    login       = profile.get("login", "")
    repos       = profile.get("public_repos", 0)
    followers   = profile.get("followers", 0)
    following   = profile.get("following", 0)
    bio         = profile.get("bio") or ""
    blog        = profile.get("blog") or ""
    name        = profile.get("name") or ""
    created_raw = profile.get("created_at", "")
    gists       = profile.get("public_gists", 0)

    # ── Strong signals (1 is enough) ─────────────────────────────────────
    if SPAM_BIO_KEYWORDS.search(bio):
        return True, f"spam keyword in bio: '{SPAM_BIO_KEYWORDS.search(bio).group(0)}'"

    if SPAM_LINK_PATTERNS.search(blog):
        return True, f"suspicious link in profile: '{blog[:60]}'"

    sus_username, username_reason = _username_is_suspicious(login)
    if sus_username and (repos == 0 or following > max(followers, 1) * 5):
        # Obvious bot username + hollow OR mass-following = strong enough alone
        extra = "0 repos" if repos == 0 else f"{following} following / {followers} followers"
        return True, f"{username_reason} | {extra}"

    # ── Weak signals (need 2+, or 1 + suspicious username) ───────────────
    signals: list[str] = []

    # Hollow profile
    if repos == 0 and gists == 0 and not bio.strip() and not name.strip():
        signals.append("hollow profile (0 repos, 0 gists, no name/bio)")

    # Very new account
    if created_raw:
        try:
            created_at = datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
            age_days = (datetime.now(timezone.utc) - created_at).days
            if age_days < min_account_age_days:
                signals.append(f"very new account ({age_days}d old)")
        except ValueError:
            pass

    # Mass-following / follow-churn (relaxed thresholds)
    if following >= 50:
        if followers == 0:
            signals.append(f"follow-churn bot ({following} following, 0 followers)")
        else:
            ratio = following / max(followers, 1)
            if ratio >= 10:
                signals.append(f"high follow ratio ({following}/{followers} = {ratio:.0f}x)")

    # Mass-following with zero content
    if following >= 100 and repos == 0 and not bio.strip():
        signals.append(f"mass-following with no content ({following} following, 0 repos)")

    if len(signals) >= 2:
        return True, " | ".join(signals)
    if len(signals) == 1 and sus_username:
        return True, signals[0] + " | " + username_reason

    return False, ""


# ─────────────────────────────────────────────
#  Main Manager
# ─────────────────────────────────────────────
class GitHubFollowerManager:
    """GitHub follower management with spam detection, blocking, and removal."""

    # Verified orgs/accounts that should never be touched
    VERIFIED_PROTECTED = {
        'github', 'microsoft', 'google', 'facebook', 'twitter', 'vercel',
        'netlify', 'aws', 'cloudflare', 'gitlab', 'stackoverflow', 'npmjs'
    }

    def __init__(self):
        self.session  = self._create_session()
        self.username = os.getenv('GITHUB_USERNAME')
        self.token    = os.getenv('GITHUB_TOKEN')

        if not self.username or not self.token:
            raise ValueError("GITHUB_USERNAME and GITHUB_TOKEN environment variables are required.")

        self.session.headers.update({
            'Authorization': f'token {self.token}',
            'Accept': 'application/vnd.github.v3+json',
            'X-GitHub-Api-Version': '2022-11-28',
        })

        self.exceptions = self._load_exceptions()

    # ── Session ───────────────────────────────
    def _create_session(self) -> Session:
        session = Session()
        retry   = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=20)
        session.mount('http://',  adapter)
        session.mount('https://', adapter)
        return session

    # ── Persistence ───────────────────────────
    def _load_exceptions(self) -> Set[str]:
        """Load usernames that should never be touched (exceptions.txt)."""
        if not os.path.exists("exceptions.txt"):
            return set()
        with open("exceptions.txt", "r") as f:
            return {line.strip().lower() for line in f if line.strip() and not line.startswith("#")}

    def _load_blocked_log(self) -> Set[str]:
        """Load previously blocked/removed usernames to skip re-processing."""
        if not os.path.exists("spam_blocked.txt"):
            return set()
        with open("spam_blocked.txt", "r") as f:
            return {line.strip().lower() for line in f if line.strip()}

    def _log_blocked(self, username: str, reason: str):
        with open("spam_blocked.txt", "a") as f:
            f.write(f"{username}\n")
        with open("spam_log.txt", "a") as f:
            f.write(f"{datetime.now().isoformat()} | BLOCKED | @{username} | {reason}\n")

    def _log_action(self, action: str, username: str, detail: str = ""):
        with open("spam_log.txt", "a") as f:
            f.write(f"{datetime.now().isoformat()} | {action} | @{username} | {detail}\n")

    # ── API helpers ───────────────────────────
    def _paginated_fetch(self, url: str) -> List:
        results = []
        while url:
            resp = self.session.get(url)
            if resp.status_code != 200:
                break
            results.extend(resp.json())
            url = resp.links.get('next', {}).get('url')
        return results

    def _get_user_profile(self, username: str) -> Optional[dict]:
        resp = self.session.get(f'https://api.github.com/users/{username}')
        if resp.status_code == 200:
            return resp.json()
        return None

    def _is_protected(self, username: str) -> bool:
        u = username.lower()
        return u in self.VERIFIED_PROTECTED or u in self.exceptions

    # ── Spam actions ──────────────────────────
    def _block_user(self, username: str) -> tuple[bool, int]:
        """Block a user. Returns (success, http_status_code)."""
        resp = self.session.put(f'https://api.github.com/user/blocks/{username}')
        return resp.status_code == 204, resp.status_code

    def _unblock_user(self, username: str) -> tuple[bool, int]:
        """Unblock a user. Returns (success, http_status_code)."""
        resp = self.session.delete(f'https://api.github.com/user/blocks/{username}')
        return resp.status_code == 204, resp.status_code

    def _remove_follower(self, username: str) -> tuple[bool, str]:
        """
        Remove a follower via block→unblock trick.
        Returns (success, detail_message).
        """
        blocked, block_code = self._block_user(username)
        if not blocked:
            if block_code == 422:
                # 422 = account suspended by GitHub — block not needed, they're already restricted
                # They will naturally drop from follower count as GitHub purges suspended accounts
                return False, f"account suspended by GitHub (block returned {block_code})"
            if block_code == 404:
                return False, f"account not found/deleted (block returned {block_code})"
            return False, f"block failed with HTTP {block_code} — check token has 'Block and unblock users: Read and write' permission"

        time.sleep(0.3)
        unblocked, unblock_code = self._unblock_user(username)
        if unblocked:
            return True, "block+unblock succeeded"
        return False, f"block succeeded but unblock failed with HTTP {unblock_code}"

    def _unfollow_user(self, username: str) -> bool:
        resp = self.session.delete(f'https://api.github.com/user/following/{username}')
        return resp.status_code == 204

    def _follow_user(self, username: str) -> bool:
        resp = self.session.put(f'https://api.github.com/user/following/{username}')
        return resp.status_code == 204

    # ── Main flows ────────────────────────────
    def scan_and_purge_spam(self, block_and_keep: bool = False):
        """
        Scan all current followers for spam accounts.
        For each detected spam account:
          - If you are following them → unfollow
          - Block them (removes them from your followers list)
          - Optionally keep them blocked (block_and_keep=True) or unblock after removal

        Args:
            block_and_keep: True  → permanently block the spam account.
                            False → block-then-unblock (removes follower, stays unblocked).
        """
        print(f"\n🔍 Scanning followers of @{self.username} for spam accounts …\n")

        followers_url = f'https://api.github.com/users/{self.username}/followers?per_page=100'
        following_url = f'https://api.github.com/users/{self.username}/following?per_page=100'

        followers_raw = self._paginated_fetch(followers_url)
        following_set = {u['login'].lower() for u in self._paginated_fetch(following_url)}
        already_blocked = self._load_blocked_log()

        followers = [u['login'] for u in followers_raw]
        print(f"📊 {len(followers)} followers found. Checking each profile …\n")

        spam_found     = []
        spam_skipped   = []
        errors         = []

        for login in followers:
            login_lower = login.lower()

            if self._is_protected(login_lower):
                continue
            if login_lower in already_blocked:
                print(f"  ⏭️  Already handled: @{login}")
                spam_skipped.append(login)
                continue

            profile = self._get_user_profile(login)
            if not profile:
                print(f"  ⚠️  Could not fetch profile for @{login}")
                errors.append(login)
                time.sleep(0.5)
                continue

            flagged, reason = is_spam_account(profile)

            if flagged:
                print(f"  🚨 SPAM detected: @{login}")
                print(f"     Reason: {reason}")

                # 1. Unfollow if we were following them
                if login_lower in following_set:
                    if self._unfollow_user(login):
                        print(f"     ✓ Unfollowed @{login}")
                        self._log_action("UNFOLLOWED", login, reason)
                    time.sleep(0.4)

                # 2. Block (and optionally keep blocked)
                if block_and_keep:
                    ok, code = self._block_user(login)
                    if ok:
                        print(f"     🚫 Blocked @{login} (permanent)")
                        self._log_blocked(login, reason)
                    else:
                        print(f"     ❌ Block failed for @{login} — HTTP {code}")
                        errors.append(login)
                else:
                    # Block-then-unblock: removes from followers without permanent block
                    ok, detail = self._remove_follower(login)
                    if ok:
                        print(f"     ✓ Removed from followers @{login} (block+unblock)")
                        self._log_blocked(login, reason)
                    else:
                        print(f"     ❌ Remove-follower failed for @{login}: {detail}")
                        errors.append(login)

                spam_found.append(login)
                time.sleep(0.6)
            else:
                print(f"  ✅ OK: @{login}")
                time.sleep(0.2)

        # Summary
        print("\n" + "=" * 50)
        print(f"🚨 Spam accounts processed : {len(spam_found)}")
        print(f"⏭️  Already handled (skipped): {len(spam_skipped)}")
        print(f"❌ Errors                   : {len(errors)}")
        if spam_found:
            print(f"\nBlocked/removed accounts:")
            for u in spam_found:
                print(f"  • @{u}")
        if errors:
            print(f"\nFailed accounts (check token has 'user:block' scope):")
            for u in errors:
                print(f"  • @{u}")
        print("=" * 50)
        print(f"\n📄 Full log written to spam_log.txt")

        # Return the set of spam logins found this session
        # so sync_follows() can exclude them without re-fetching
        return {u.lower() for u in spam_found}

    def sync_follows(self, known_spam: Set[str] = None):
        """
        Reciprocal-follow sync:
          - Unfollow anyone not following back (skip protected & spam)
          - Follow back anyone who follows you but you don't follow,
            AFTER verifying they are not a spam account.

        Args:
            known_spam: Set of logins already flagged as spam (from scan_and_purge_spam).
                        sync_follows also loads spam_blocked.txt and re-checks each
                        candidate before following back.
        """
        print(f"\n🔄 Syncing follows for @{self.username} …\n")

        followers_url = f'https://api.github.com/users/{self.username}/followers?per_page=100'
        following_url = f'https://api.github.com/users/{self.username}/following?per_page=100'

        followers = {u['login'].lower() for u in self._paginated_fetch(followers_url)}
        following = {u['login'].lower() for u in self._paginated_fetch(following_url)}

        # Build a combined spam exclusion list:
        #   • accounts passed in from spam scan this session
        #   • accounts previously blocked (spam_blocked.txt)
        spam_exclusions = set(known_spam or set())
        spam_exclusions |= self._load_blocked_log()

        print(f"📊 {len(followers)} followers | {len(following)} following")
        print(f"🚫 {len(spam_exclusions)} spam exclusions loaded\n")

        not_following_back = following - followers
        not_followed_back  = followers - following

        unfollowed, followed, spam_skipped, ghost_removed = [], [], [], []

        # ── Unfollow non-reciprocal (skip protected & known spam) ──────────
        for user in not_following_back:
            if self._is_protected(user):
                print(f"  🛡️ Protected – skip: @{user}")
                continue
            if user in spam_exclusions:
                # Already blocked/removed — also unfollow if still following
                if self._unfollow_user(user):
                    print(f"  🚫 Unfollowed known spam: @{user}")
                    unfollowed.append(user)
                continue
            if self._unfollow_user(user):
                unfollowed.append(user)
                print(f"  ✓ Unfollowed: @{user}")
            time.sleep(0.5)

        # ── Follow back — but verify not spam first ─────────────────────────
        for user in not_followed_back:
            if self._is_protected(user):
                continue

            # Skip if already known spam
            if user in spam_exclusions:
                print(f"  🚨 Skip follow-back (known spam): @{user}")
                spam_skipped.append(user)
                continue

            # Fetch profile and run spam check before following back
            profile = self._get_user_profile(user)
            if profile:
                flagged, reason = is_spam_account(profile)
                if flagged:
                    print(f"  🚨 Spam detected at follow-back stage: @{user} ({reason})")
                    self._remove_follower(user)
                    self._log_blocked(user, f"[sync-stage] {reason}")
                    spam_skipped.append(user)
                    time.sleep(0.6)
                    continue

            # Attempt follow-back
            follow_resp = self.session.put(f'https://api.github.com/user/following/{user}')
            if follow_resp.status_code == 204:
                followed.append(user)
                print(f"  ✓ Followed back: @{user}")
            else:
                # Follow failed → account is suspended, deleted, or restricted by GitHub
                # (no follow button on their profile). Try to remove from followers.
                print(f"  👻 Ghost/restricted: @{user} (follow returned {follow_resp.status_code}) — removing")
                ghost_removed.append(user)  # count it regardless of whether removal succeeds
                ok, detail = self._remove_follower(user)
                if ok:
                    self._log_action("REMOVED_GHOST", user, f"follow HTTP {follow_resp.status_code} | {detail}")
                    print(f"     ✓ Removed from followers")
                else:
                    self._log_action("REMOVE_GHOST_FAILED", user, f"follow HTTP {follow_resp.status_code} | {detail}")
                    print(f"     ⚠️  Could not remove: {detail}")
            time.sleep(0.5)

        print("\n" + "=" * 40)
        print(f"✅ Followed back      : {len(followed)}")
        print(f"🗑️  Unfollowed         : {len(unfollowed)}")
        print(f"👻 Ghost/restricted   : {len(ghost_removed)} detected ({len([u for u in ghost_removed if u not in spam_skipped])} removal failed)")
        print(f"🚨 Spam skipped       : {len(spam_skipped)}")
        print(f"🛡️  Protected          : {len([u for u in not_following_back if self._is_protected(u)])}")
        print("=" * 40)


# ─────────────────────────────────────────────
#  Entry Point
# ─────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(description="GitHub Follower Manager")
    parser.add_argument(
        "--mode",
        choices=["sync", "spam", "all"],
        default="spam",
        help=(
            "sync  – reciprocal follow/unfollow only\n"
            "spam  – scan followers and remove/block spam accounts\n"
            "all   – spam scan first, then sync (default: spam)"
        )
    )
    parser.add_argument(
        "--block-keep",
        action="store_true",
        default=False,
        help="Permanently block spam accounts instead of block-then-unblock."
    )
    args = parser.parse_args()

    try:
        manager = GitHubFollowerManager()

        spam_set = set()
        if args.mode in ("spam", "all"):
            spam_set = manager.scan_and_purge_spam(block_and_keep=args.block_keep)

        if args.mode in ("sync", "all"):
            # Pass spam accounts found this session so sync doesn't follow them back
            manager.sync_follows(known_spam=spam_set)

        return 0
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
