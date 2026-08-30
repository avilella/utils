
python ./bluesky.py -m searching --keywords bioinformatics.txt --export bioinformatics.20260830.tsv --creds bluesky.txt --limit 20000
cat bioinformatics.20260830.tsv | sed 's/\r//g' | csvtk transpose -t -I | csvtk transpose -t > bioinformatics.20260830.filt.tsv
python ./check_followers.py bluesky.txt albertvilella.bsky.social bioinformatics.20260830.filt.tsv
python predict_followers.py --new-following --creds bluesky.txt -i bioinformatics.20260830.filt.tsv --followers matches_following_albertvilella.bsky.social.tsv --limit 100 --tag 20260830 --verbose

