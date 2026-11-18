import os
import re
import sys
import time
from typing import List, Tuple, Optional
import requests

# ─────────────────────────────────────────────
#  Spam Detection Heuristics
# ─────────────────────────────────────────────

SPAM_BIO_PATTERNS = re.compile(
    r'\bspam\s+(?:follow|following|acc|account|bot)\b|'
    r'\b(?:follow|check)\s+(?:my\s+)?main\b|'
    r'\bmain\s+(?:acc|account)\s*[@:]|'
    r'\balt\s+(?:acc|account)\b|'
    r'\bblock\s+if\s+unwanted\b|'
    r'crypto|bitcoin|nft|forex|trading|profit|earn\s+money|'
    r'onlyfans|adult|escort|porn|xxx|casino|gambling|'
    r'instagram\s+follower|tiktok\s+follower|youtube\s+subscriber|'
    r'follow\s+back\s+or\s+unfollow',
    re.IGNORECASE
)

SPAM_LINK_PATTERNS = re.compile(
    r'bit\.ly|tinyurl|t\.co|goo\.gl|ow\.ly|rb\.gy|cutt\.ly|'
    r'telegram\.me|t\.me|wa\.me|discord\.gg',
    re.IGNORECASE
)

REPEATED_CHARS = re.compile(r'(.)\1{4,}')


def evaluate_account(profile: dict) -> Tuple[bool, str]:
    """
    Returns (is_spam, reason).
    Targeted at actual spam/bot networks:
      - Explicit spam / alt-bot redirection phrases in bio
      - Suspicious links in profile with 0 repos
      - Flagged / shadowbanned bot anomaly (GitHub zeroes following & followers to 0)
      - Extreme follow-churn bots (hundreds of followings, 0 followers, 0 repos)
    """
    login       = profile.get("login", "")
    repos       = profile.get("public_repos", 0)
    followers   = profile.get("followers", 0)
    following   = profile.get("following", 0)
    bio         = profile.get("bio") or ""
    blog        = profile.get("blog") or ""
    name        = profile.get("name") or ""

    # Rule 1: Explicit spam/bot phrase in bio
    m = SPAM_BIO_PATTERNS.search(bio)
    if m:
        return True, f"Spam keywords in bio: '{m.group(0)}'"

    # Rule 2: Phishing/shortlink in website with 0 repos
    m_link = SPAM_LINK_PATTERNS.search(blog)
    if m_link and repos == 0:
        return True, f"Suspicious link in profile: '{blog[:60]}'"

    # Rule 3: Flagged / shadowbanned ghost bot anomaly
    # If an account follows you, following should normally be >= 1.
    # When GitHub flags/restricts bot networks, it zeroes out followers and following to 0.
    if following == 0 and followers == 0:
        if re.search(r'@[A-Za-z0-9_-]+', bio):
            return True, f"Flagged bot redirecting to: '{bio.strip()}'"
        if REPEATED_CHARS.search(login):
            return True, f"Flagged bot with generated username ('{login}')"
        if repos <= 2 and not name.strip():
            return True, "Flagged/shadowbanned ghost account (0 followers, 0 following, no repos/name)"

    # Rule 4: Extreme follow-churn bot
    if following >= 200 and followers == 0 and repos == 0 and not bio.strip():
        return True, f"Follow-churn bot ({following} following, 0 followers, 0 repos)"

    return False, ""


# ─────────────────────────────────────────────
#  Scanner & Interactive Blocker
# ─────────────────────────────────────────────

class SpamFollowerFinder:
    def __init__(self, username: str, token: str):
        self.username = username
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28"
        })

    def fetch_all_followers(self) -> List[dict]:
        """Fetch all followers of the user."""
        followers = []
        url = f"https://api.github.com/users/{self.username}/followers?per_page=100"
        while url:
            resp = self.session.get(url)
            if resp.status_code != 200:
                print(f"\n❌ Failed to fetch followers: HTTP {resp.status_code}")
                print(f"Response: {resp.text}")
                raise RuntimeError("Failed to fetch GitHub followers.")
            followers.extend(resp.json())
            url = resp.links.get("next", {}).get("url")
        return followers

    def get_profile(self, login: str) -> Optional[dict]:
        resp = self.session.get(f"https://api.github.com/users/{login}")
        if resp.status_code == 200:
            return resp.json()
        return None

    def block_user(self, login: str) -> bool:
        """Permanently blocks the user, which also removes them from your followers."""
        resp = self.session.put(f"https://api.github.com/user/blocks/{login}")
        return resp.status_code == 204

    def run(self, auto_block=False):
        print(f"\n🔍 Fetching followers for @{self.username} ...")
        raw_followers = self.fetch_all_followers()
        total = len(raw_followers)
        print(f"📊 Found {total} followers. Scanning for spam/bot accounts ...\n")

        flagged_accounts = []

        for idx, item in enumerate(raw_followers, 1):
            login = item["login"]
            sys.stdout.write(f"\r[{idx}/{total}] Checking @{login:<25}")
            sys.stdout.flush()

            profile = self.get_profile(login)
            if not profile:
                continue

            is_spam, reason = evaluate_account(profile)
            if is_spam:
                flagged_accounts.append((profile, reason))
                sys.stdout.write(f"\n  🚨 FLAGGED: @{login} -> {reason}\n")

            time.sleep(0.15)  # Respect rate limits

        print(f"\n\n{'=' * 50}")
        print(f"Scan complete: {len(flagged_accounts)} spam accounts identified out of {total} followers.")
        print(f"{'=' * 50}\n")

        if not flagged_accounts:
            print("✅ No spam accounts detected!")
            return

        # ── Review & Block ────────────
        blocked_count = 0
        skipped_count = 0

        if auto_block:
            print("⚡ Automated mode: blocking all detected spam accounts ...\n")
            for profile, reason in flagged_accounts:
                login = profile.get("login")
                if self.block_user(login):
                    print(f"🚫 Blocked & removed: @{login} ({reason})")
                    blocked_count += 1
                else:
                    print(f"❌ Failed to block: @{login}")
                time.sleep(0.3)
        else:
            print("Review flagged accounts and choose which ones to block:\n")
            block_all = False

            for profile, reason in flagged_accounts:
                login = profile.get("login")
                bio = profile.get("bio") or "(no bio)"
                repos = profile.get("public_repos", 0)
                flwrs = profile.get("followers", 0)
                flwng = profile.get("following", 0)

                print("-" * 50)
                print(f"👤 User      : @{login} (https://github.com/{login})")
                print(f"🚩 Reason    : {reason}")
                print(f"📝 Bio       : {bio.strip()}")
                print(f"📊 Stats     : {repos} repos | {flwrs} followers | {flwng} following")

                if block_all:
                    action = 'y'
                else:
                    while True:
                        prompt = f"Block @{login} and remove from followers? [y]es / [n]o / [a]ll / [q]uit: "
                        action = input(prompt).strip().lower()
                        if action in ('y', 'n', 'a', 'q'):
                            break

                if action == 'q':
                    print("\n⏹️ Quitting review.")
                    break
                elif action == 'a':
                    block_all = True
                    action = 'y'

                if action == 'y':
                    if self.block_user(login):
                        print(f"🚫 Successfully blocked @{login}")
                        blocked_count += 1
                    else:
                        print(f"❌ Failed to block @{login}")
                else:
                    print(f"⏭️ Skipped @{login}")
                    skipped_count += 1

                time.sleep(0.2)

        print("\n" + "=" * 50)
        print(f"✅ Blocked & removed : {blocked_count}")
        print(f"⏭️ Skipped           : {skipped_count}")
        print("=" * 50)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Find and Block GitHub Spam Followers")
    parser.add_argument(
        "--auto-block",
        action="store_true",
        default=os.getenv("CI") == "true",
        help="Automatically block all detected spam accounts without prompting (default in CI)"
    )
    args = parser.parse_args()

    username = os.getenv("GITHUB_USERNAME")
    token = os.getenv("GITHUB_TOKEN")

    if not username:
        username = input("Enter your GitHub username: ").strip()
    if not token:
        token = input("Enter your GitHub Personal Access Token: ").strip()

    if not username or not token:
        print("❌ Username and token are required.")
        return 1

    finder = SpamFollowerFinder(username, token)
    finder.run(auto_block=args.auto_block)
    return 0


if __name__ == "__main__":
    exit(main())

