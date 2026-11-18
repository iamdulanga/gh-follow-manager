"""Quick check: which follower are you NOT following back?"""
import os, requests

username = os.getenv("GITHUB_USERNAME") or input("GitHub username: ").strip()
token = os.getenv("GITHUB_TOKEN") or input("GitHub token: ").strip()

s = requests.Session()
s.headers.update({"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"})

def fetch_all(url):
    users = []
    while url:
        r = s.get(url)
        if r.status_code != 200: break
        users.extend(u["login"] for u in r.json())
        url = r.links.get("next", {}).get("url")
    return set(users)

followers = fetch_all(f"https://api.github.com/users/{username}/followers?per_page=100")
following = fetch_all(f"https://api.github.com/users/{username}/following?per_page=100")

not_followed_back = followers - following

print(f"\nFollowers: {len(followers)} | Following: {len(following)}")
print(f"Not followed back: {len(not_followed_back)}\n")
for u in sorted(not_followed_back):
    r = s.get(f"https://api.github.com/users/{u}")
    p = r.json() if r.status_code == 200 else {}
    print(f"  @{u} — repos:{p.get('public_repos','?')} followers:{p.get('followers','?')} following:{p.get('following','?')} bio:{(p.get('bio') or '(none)')[:60]}")

