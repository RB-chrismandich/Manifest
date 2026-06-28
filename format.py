import re
with open('.jules/palette.md', 'r') as f:
    text = f.read()

# I will just write a new entry since this is getting messy
# Let's restore from HEAD and then append cleanly.
