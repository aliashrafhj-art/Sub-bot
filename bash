# ১. ফাইল রিনেম
mv single_bot.py main.py

# ২. railway.json চেক করুন (main.py থাকা উচিত)
cat railway.json

# ৩. গিট আপডেট
git add main.py
git add railway.json
git rm single_bot.py
git commit -m "fix: renamed to main.py for proper start command"
git push
