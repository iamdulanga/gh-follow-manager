[![Run GH Follow Manager](https://github.com/iamdulanga/gh-follow-manager/actions/workflows/run-script.yml/badge.svg)](https://github.com/iamdulanga/gh-follow-manager/actions/workflows/run-script.yml)

# GitHub Follower-Following Manager 

This Python script helps you manage your GitHub followers and following lists. It identifies users you're following who don't follow you back and users who follow you but whom you're not following back. You can also automate following or unfollowing based on these lists.


## Features

- **Follower vs Following Comparison**:  
  Easily see who isn't following you back and who you're not following back.  
- **Automated Management**:  
  - Unfollow users who don't follow you back.  
  - Follow users who follow you but whom you're not following.  
- **Detailed Output**:  
  Prints lists of discrepancies for easy review.  


## Requirements

- **Python 3.x**  
- **Requests library** (Install using `pip install requests`)  


## How It Works

1. **Authentication**:  
   The script uses your GitHub username and personal access token to access the GitHub API.  
2. **Comparison**:  
   It fetches the lists of your followers and following, then compares them to identify differences.  
3. **Automated Actions**:  
   - Unfollows users who don't follow you back.  
   - Follows users who follow you but whom you're not following.  
4. **Output**:  
   Displays two lists:  
   - Users you're following but who don't follow you back.  
   - Users following you but whom you're not following.  


## Usage

1. Clone this repository:
   ```bash
   git clone https://github.com/your_username/github-follow-analyzer.git
   cd github-follow-analyzer
   ```
2. Replace the placeholders in the script:  
   - `'your_github_username'`: Your GitHub username.  
   - `'GITHUB_TOKEN'`: Your personal access token.  
3. Run the script:
   ```bash
   python github_follow_analyzer.py
   ```
4. Review the output and check the automated actions.


## Troubleshooting

### Common Issues and Fixes:

#### 1. **Unfollowing Doesn't Work**:
   - Ensure the access token has the correct permissions (the `user` scope).  
   - Check the API response for errors or rate limits:
     ```python
     print(response.status_code, response.text)
     ```
   - Verify that the API endpoint is correct:
     ```
     DELETE https://api.github.com/user/following/{username}
     ```

#### 2. **API Rate Limits**:
   - GitHub's API allows 5,000 requests per hour for authenticated users.  
   - Check your remaining requests using:
     ```python
     rate_limit_url = 'https://api.github.com/rate_limit'
     response = requests.get(rate_limit_url, headers=headers)
     print(response.json())
     ```
   - Add delays between requests to avoid hitting limits:
     ```python
     time.sleep(1)  # Add a 1-second delay
     ```

#### 3. **Token Issues**:
   - Ensure the token is valid and has not expired.  
   - Regenerate the token if needed and update it in the script.  

#### 4. **Environment Variables for Security**:
   - Avoid hardcoding your token in the script. Use environment variables instead:
     ```python
     import os
     token = os.getenv('GITHUB_TOKEN')
     ```


## Example Output

```plaintext
Accounts you're following but not following you back:
{'user1', 'user2', 'user3'}

Accounts following you but you're not following back:
{'user4', 'user5'}
```


## Notes

- This script is for personal use and respects GitHub's API terms.  
- Be mindful of your connections before automating follow/unfollow actions.  
- Always review the lists before making changes.

---

# Steps to Automate the Script Using GitHub Actions

## 1. Create a Workflow File
In your repository, create the directory `.github/workflows` if it doesn't exist. Then, create a file named `run-script.yml` inside it.

## 2. Add the Workflow Configuration
Copy the following content into the `run-script.yml` file:

```yaml
name: Run GitHub Follower-Following Manager

on:
  schedule:
    # Runs at 00:00 UTC every Sunday
    - cron: '0 0 * * 0'

jobs:
  run-script:
    runs-on: ubuntu-latest

    steps:
      # Step 1: Check out the repository
      - name: Checkout repository
        uses: actions/checkout@v3

      # Step 2: Set up Python
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.x'

      # Step 3: Install dependencies
      - name: Install dependencies
        run: pip install requests

      # Step 4: Run the script
      - name: Run the script
        env:
          GITHUB_USERNAME: ${{ secrets.GITHUB_USERNAME }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: python github_follow_analyzer.py
```

## 3. Store Secrets in GitHub
- Go to your repository on GitHub.
- Navigate to **Settings** > **Secrets and variables** > **Actions**.
- Add the following secrets:
  - `GITHUB_USERNAME`: Your GitHub username.
  - `GITHUB_TOKEN`: Your personal access token with the required permissions.

## 4. Modify Your Script to Use Environment Variables
Update your script to fetch the username and token from environment variables:

```python
import os

username = os.getenv('GITHUB_USERNAME')
token = os.getenv('GITHUB_TOKEN')

headers = {
    'Authorization': f'token {token}',
    'Accept': 'application/vnd.github.v3+json'
}
```

## 5. Commit and Push
Commit your changes and push them to the repository. The workflow will now run every Sunday at midnight UTC.

## 6. Verify the Setup
- Check the **Actions** tab in your repository to monitor workflow runs.
- If there are any issues, logs will help you debug them.

---

## The cron syntax in GitHub Actions defines when a workflow runs. It has five fields:

```sql
┌───────────── minute (0-59)
│ ┌─────────── hour (0-23)
│ │ ┌───────── day of the month (1-31)
│ │ │ ┌─────── month (1-12)
│ │ │ │ ┌───── day of the week (0-7) (0 and 7 both represent Sunday)
│ │ │ │ │
│ │ │ │ │
* * * * *
```
### Examples:

Run Every 1 Hour:

 - Use 0 * * * *.
 - This means: At the 0th minute of every hour (e.g., 1:00, 2:00, 3:00, etc.).
```yaml
- cron: '0 * * * *'
```

Run on Monday at 8 AM:

 - Use 0 8 * * 1.
 - This means: At 8:00 AM every Monday (day of the week 1).
```yaml
- cron: '0 8 * * 1'
```

Run on Thursday at 10 PM:

 - Use 0 22 * * 4.
 - This means: At 10:00 PM every Thursday (day of the week 4).
```yaml
- cron: '0 22 * * 4'
```

### Explanation of Common Patterns:
- "*"means "every."
- Numbers specify exact times (e.g., 8 for 8 AM or 22 for 10 PM).
- Day of the week:
  - 0 or 7 = Sunday
  - 1 = Monday
  - 2 = Tuesday, and so on.

