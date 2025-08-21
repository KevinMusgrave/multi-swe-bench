#!/bin/bash
set -e

# Check if there are any changes in the git repository
if [ -n "$(git status --porcelain)" ]; then
  echo "There are changes in the git repository"
  git status
  exit 1
else
  echo "No changes in the git repository"
  exit 0
fi