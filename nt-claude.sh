#!/usr/bin/env bash
# ~/bin/nt-claude.sh
msg=$(python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('last_assistant_message','')[:200])")
~/bin/nt "Claude: ${msg:-done}"
