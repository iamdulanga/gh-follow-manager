# GitHub Follower-Following Comparator

This Python program compares your GitHub followers and following lists. It identifies accounts that you're following but aren't following you back and vice versa. The program helps you keep track of your connections on GitHub.

## Features

- **Follower vs Following Comparison:** Easily see who isn't following you back and who you're not following back.
- **Simple and Clean:** No auto-unfollow feature, giving you full control over your connections.

## How It Works

1. **Authentication:** The program uses your GitHub username and personal access token to access the GitHub API.
2. **Comparison:** It fetches the lists of your followers and following, then compares them to identify differences.
3. **Output:** The program prints out two lists:
   - Users you follow but who don't follow you back.
   - Users who follow you but whom you're not following back.

## Requirements

- Python 3.x
- `requests` library

Install the `requests` library if you haven't already:

```bash
pip install requests
```

## Usage

1. Clone this repository.
2. Replace `'your_github_username'` and `'your_github_token'` in the script with your GitHub credentials.
3. Run the script:

```bash
python compare_github_followers.py
```

4. Review the output to see who you might want to unfollow or follow back.

## Disclaimer

This program respects your privacy and does not perform any actions on your behalf (like unfollowing users). It’s designed to help you analyze your GitHub connections manually.

---