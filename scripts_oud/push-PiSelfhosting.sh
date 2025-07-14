#!/bin/bash

# push-PiSelfhosting.sh
# A utility script to quickly add, commit, and push all changes to GitHub for PiSelfhosting.

# Check if a commit message was provided
if [ -z "$1" ]; then
  echo "Error: Please provide a commit message as an argument."
  echo "Usage: ./push-PiSelfhosting.sh \"Your commit message here\""
  exit 1
fi

# Store the commit message from the first argument
COMMIT_MESSAGE="$1"

echo "---"
echo "Starting Git operations for PiSelfhosting..."
echo "---"

# Display the current Git status before proceeding.
# This helps you review changes before they are added and committed.
echo "Current Git status:"
git status
echo "---"
echo "Review the changes above. Press Enter to continue or Ctrl+C to abort."
read -r # Wait for user to press Enter

# 1. Add all changes to the staging area
echo "Staging all changes with 'git add .'"
git add .

# Check if 'git add .' was successful before proceeding
if [ $? -ne 0 ]; then
  echo "Error: 'git add .' failed. Please check your Git repository."
  exit 1
fi

# 2. Commit the staged changes with the provided message
echo "Committing changes with message: \"$COMMIT_MESSAGE\""
git commit -m "$COMMIT_MESSAGE"

# Check if 'git commit' was successful
if [ $? -ne 0 ]; then
  echo "Error: 'git commit' failed. This might happen if there are no changes to commit."
  exit 1
fi

# 3. Push the committed changes to the 'main' branch on GitHub
echo "Pushing changes to 'origin main'..."
git push origin main

# Check if 'git push' was successful
if [ $? -ne 0 ]; then
  echo "Error: 'git push origin main' failed. Check your network connection or Git credentials."
  exit 1
fi

echo "---"
echo "All Git operations completed successfully!"
echo "---"
