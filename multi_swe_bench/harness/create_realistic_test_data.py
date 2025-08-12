#!/usr/bin/env python3
"""
Create realistic test data with actual commit hashes from real repositories.

This script fetches real PR data from GitHub to create valid test instances
that can be used with the batch build system.
"""

import json
import requests
import sys
from pathlib import Path
from typing import Dict, List, Optional

def get_github_pr_data(org: str, repo: str, pr_number: int, token: Optional[str] = None) -> Optional[Dict]:
    """Fetch PR data from GitHub API"""
    
    headers = {'Accept': 'application/vnd.github.v3+json'}
    if token:
        headers['Authorization'] = f'token {token}'
    
    # Get PR data
    pr_url = f"https://api.github.com/repos/{org}/{repo}/pulls/{pr_number}"
    
    try:
        response = requests.get(pr_url, headers=headers)
        response.raise_for_status()
        pr_data = response.json()
        
        if pr_data['state'] != 'closed' or not pr_data['merged']:
            print(f"⚠️  PR {org}/{repo}#{pr_number} is not merged, skipping")
            return None
        
        # Get commit data
        commits_url = f"https://api.github.com/repos/{org}/{repo}/pulls/{pr_number}/commits"
        commits_response = requests.get(commits_url, headers=headers)
        commits_response.raise_for_status()
        commits = commits_response.json()
        
        if not commits:
            print(f"⚠️  No commits found for PR {org}/{repo}#{pr_number}")
            return None
        
        # Get the base commit (what the PR was based on)
        base_sha = pr_data['base']['sha']
        
        # Get diff/patch data
        patch_url = f"https://api.github.com/repos/{org}/{repo}/pulls/{pr_number}"
        patch_headers = headers.copy()
        patch_headers['Accept'] = 'application/vnd.github.v3.diff'
        
        patch_response = requests.get(patch_url, headers=patch_headers)
        patch_response.raise_for_status()
        patch_content = patch_response.text
        
        # Try to get linked issues
        issues = []
        if pr_data.get('body'):
            # Simple regex to find issue references
            import re
            issue_refs = re.findall(r'(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#(\d+)', 
                                  pr_data['body'], re.IGNORECASE)
            
            for issue_num in issue_refs[:3]:  # Limit to first 3 issues
                issue_url = f"https://api.github.com/repos/{org}/{repo}/issues/{issue_num}"
                try:
                    issue_response = requests.get(issue_url, headers=headers)
                    if issue_response.status_code == 200:
                        issue_data = issue_response.json()
                        issues.append({
                            "number": int(issue_num),
                            "title": issue_data.get('title', ''),
                            "body": issue_data.get('body', '')
                        })
                except:
                    pass
        
        # Create instance data
        instance = {
            "org": org,
            "repo": repo,
            "number": pr_number,
            "state": "closed",
            "title": pr_data['title'],
            "body": pr_data.get('body', ''),
            "base": {
                "label": pr_data['base']['label'],
                "ref": pr_data['base']['ref'],
                "sha": base_sha
            },
            "resolved_issues": issues,
            "fix_patch": patch_content,
            "test_patch": patch_content,  # For simplicity, using same patch
            "instance_id": f"{org}__{repo}-{pr_number}"
        }
        
        print(f"✅ Successfully fetched data for {org}/{repo}#{pr_number}")
        return instance
        
    except requests.RequestException as e:
        print(f"❌ Error fetching PR {org}/{repo}#{pr_number}: {e}")
        return None
    except Exception as e:
        print(f"❌ Unexpected error for PR {org}/{repo}#{pr_number}: {e}")
        return None

def create_realistic_test_data(output_file: str = "realistic_test_instances.jsonl", 
                             github_token: Optional[str] = None):
    """Create realistic test data from actual GitHub PRs"""
    
    # List of real, merged PRs from popular repositories
    test_prs = [
        # Small, simple PRs that are likely to work
        ("google", "gson", 2043),  # Recent merged PR
        ("apache", "commons-lang", 902),  # Recent merged PR  
        ("spring-projects", "spring-boot", 32000),  # Recent merged PR
    ]
    
    instances = []
    
    print(f"🔍 Fetching data for {len(test_prs)} PRs...")
    
    for org, repo, pr_number in test_prs:
        print(f"📥 Fetching {org}/{repo}#{pr_number}...")
        
        instance = get_github_pr_data(org, repo, pr_number, github_token)
        if instance:
            instances.append(instance)
    
    if not instances:
        print("❌ No valid instances created")
        return False
    
    # Write to file
    output_path = Path(output_file)
    with open(output_path, 'w') as f:
        for instance in instances:
            f.write(json.dumps(instance) + '\n')
    
    print(f"✅ Created {len(instances)} realistic test instances in {output_file}")
    
    # Show what was created
    print("\n📋 Created instances:")
    for instance in instances:
        print(f"  - {instance['org']}/{instance['repo']}#{instance['number']}: {instance['title']}")
    
    return True

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Create realistic test data for Multi-SWE-bench")
    parser.add_argument('--output', '-o', default='realistic_test_instances.jsonl',
                       help='Output JSONL file')
    parser.add_argument('--token', '-t', help='GitHub API token (optional but recommended)')
    
    args = parser.parse_args()
    
    if not args.token:
        print("⚠️  No GitHub token provided. You may hit rate limits.")
        print("   Get a token at: https://github.com/settings/tokens")
        print("   Usage: python create_realistic_test_data.py --token YOUR_TOKEN")
    
    success = create_realistic_test_data(args.output, args.token)
    
    if success:
        print(f"\n🎉 Success! You can now test with:")
        print(f"   python quick_publish.py {args.output} --dry-run")
        return 0
    else:
        print("\n❌ Failed to create test data")
        return 1

if __name__ == "__main__":
    sys.exit(main())