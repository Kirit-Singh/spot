# The e2e/work/ dir holds Docker run outputs (root-owned, gitignored) -- keep
# pytest from recursing into it during collection.
collect_ignore = ["e2e/work"]
