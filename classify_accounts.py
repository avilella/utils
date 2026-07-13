#!/usr/bin/env python3
import argparse
import csv
import sys
import re
from pathlib import Path

# --- Classification Heuristics ---
# Words that heavily imply an organization, group, or institution
INSTITUTIONAL_KEYWORDS = [
    r"\bofficial\b", r"\binstitute\b", r"\buniversity\b", r"\bdepartment\b", 
    r"\bcenter\b", r"\bcentre\b", r"\blaboratory\b", r"\bcompany\b", 
    r"\binc\.?\b", r"\bltd\b", r"\borganization\b", r"\bsociety\b", 
    r"\bjournal\b", r"\bproject\b", r"\bconsortium\b", r"\bassociation\b", 
    r"\bfoundation\b", r"\bnetwork\b", r"\bpodcast\b", r"\bgroup\b", 
    r"\binitiative\b", r"\blab\b"
]
INST_PATTERN = re.compile("|".join(INSTITUTIONAL_KEYWORDS), re.IGNORECASE)

# Words that heavily imply an individual person
PERSONAL_KEYWORDS = [
    r"\bi\b", r"\bi'm\b", r"\bi am\b", r"\bmy\b", r"\bme\b", r"\bmine\b",
    r"he/him", r"she/her", r"they/them", r"\bopinions\b", r"\bphd student\b", 
    r"\bpostdoc\b", r"\bresearcher\b", r"\bscientist\b", r"\bengineer\b", 
    r"\bfather\b", r"\bmother\b", r"\bhusband\b", r"\bwife\b", r"\bdad\b", 
    r"\bmom\b", r"\balumnus\b", r"\balumna\b", r"\benthusiast\b", r"\bguy\b", 
    r"\bgirl\b"
]
PERS_PATTERN = re.compile("|".join(PERSONAL_KEYWORDS), re.IGNORECASE)

def classify_account(handle, display_name, bio):
    """
    Returns 'Institutional' or 'Personal' based on keyword scoring.
    Defaulting to 'Personal' if the score is tied, as that is the norm for social media.
    """
    text_to_search = f"{handle} {display_name} {bio}".replace("\n", " ").replace("\t", " ")
    
    inst_score = len(INST_PATTERN.findall(text_to_search))
    pers_score = len(PERS_PATTERN.findall(text_to_search))
    
    # Heuristic boost: If the display name directly ends in "Lab", "University", or "Institute", 
    # it's highly likely to be institutional.
    if re.search(r'\b(lab|university|institute|centre|center)$', display_name, re.IGNORECASE):
        inst_score += 3

    if inst_score > pers_score:
        return "Institutional"
    return "Personal"

def main():
    parser = argparse.ArgumentParser(description="Classify exported Bluesky accounts as Personal or Institutional.")
    parser.add_argument("-i", "--inputfile", required=True, help="Path to the input TSV file.")
    parser.add_argument("--tag", default="clas", help="Tag to append to the output filename (default: 'tool').")
    parser.add_argument("--outdir", default=None, help="Output directory. Defaults to the same directory as the input file.")
    parser.add_argument("--verbose", action="store_true", help="Print detailed processing steps to STDERR.")
    parser.add_argument("--refresh", action="store_true", help="Force recalculation. If off, checks if output exists and exits.")
    
    args = parser.parse_args()

    input_path = Path(args.inputfile)
    if not input_path.is_file():
        print(f"Error: Input file '{input_path}' does not exist.", file=sys.stderr)
        sys.exit(1)

    # Determine output directory and path
    out_dir = Path(args.outdir) if args.outdir else input_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Construct output filename: original_name(without ext).tag.csv
    out_filename = f"{input_path.stem}.{args.tag}.csv"
    out_path = out_dir / out_filename

    # --- Cache / Refresh Logic ---
    if not args.refresh:
        if out_path.exists() and out_path.stat().st_size > 0:
            if args.verbose:
                print(f"[INFO] Found existing, non-empty output file. Skipping recalculation.", file=sys.stderr)
            # ONLY STDOUT PRINT: The absolute path of the output file
            print(out_path.resolve())
            sys.exit(0)
        else:
            if args.verbose:
                print(f"[INFO] Output file missing or empty. Proceeding with calculation...", file=sys.stderr)

    # --- Processing ---
    if args.verbose:
        print(f"[INFO] Loading data from {input_path}...", file=sys.stderr)

    inst_count = 0
    pers_count = 0
    processed_count = 0

    try:
        with open(input_path, mode="r", encoding="utf-8") as infile, \
             open(out_path, mode="w", encoding="utf-8", newline="") as outfile:
            
            # Use TSV reader
            reader = csv.DictReader(infile, delimiter="\t")
            
            if not reader.fieldnames:
                print("Error: Input file appears to be empty or lacks headers.", file=sys.stderr)
                sys.exit(1)

            # Append the new column to our headers
            out_fieldnames = reader.fieldnames + ["AccountType"]
            
            # Use CSV writer for output
            writer = csv.DictWriter(outfile, fieldnames=out_fieldnames, delimiter=",")
            writer.writeheader()

            for row in reader:
                handle = row.get("Handle", "")
                display = row.get("DisplayName", "")
                bio = row.get("Bio", "")
                
                acct_type = classify_account(handle, display, bio)
                row["AccountType"] = acct_type
                writer.writerow(row)
                
                if acct_type == "Institutional":
                    inst_count += 1
                else:
                    pers_count += 1
                
                processed_count += 1
                
                if args.verbose and processed_count % 500 == 0:
                    print(f"[PROCESSING] Evaluated {processed_count} accounts...", file=sys.stderr)

    except Exception as e:
        print(f"Error during processing: {e}", file=sys.stderr)
        sys.exit(1)

    # --- Completion ---
    if args.verbose:
        print(f"\n[DONE] Successfully processed {processed_count} accounts.", file=sys.stderr)
        print(f"       -> Personal: {pers_count}", file=sys.stderr)
        print(f"       -> Institutional: {inst_count}", file=sys.stderr)
    elif processed_count > 0:
        # If not verbose, just a tiny status update to stderr
        print(f"Classified {processed_count} accounts.", file=sys.stderr)

    # ONLY STDOUT PRINT: The absolute path of the output file
    print(out_path.resolve())

if __name__ == "__main__":
    main()
