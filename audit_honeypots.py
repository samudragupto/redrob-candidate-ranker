import csv
import json
import argparse
from datetime import datetime, timedelta

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--submission', required=True)
    parser.add_argument('--candidates', required=True)
    return parser.parse_args()

def main():
    args = parse_args()
    
    # Load submission IDs
    sub_ids = []
    with open(args.submission, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            sub_ids.append(row['candidate_id'])
    
    # Pass 1: Find max last_active_date
    max_date = '1970-01-01'
    with open(args.candidates, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip(): continue
            c = json.loads(line)
            lad = c.get('redrob_signals', {}).get('last_active_date', '1970-01-01')
            if lad > max_date:
                max_date = lad
    
    max_dt = datetime.strptime(max_date, "%Y-%m-%d")
    stale_threshold = (max_dt - timedelta(days=90)).strftime("%Y-%m-%d")
    
    # Pass 2: Check each submitted candidate
    total_hp = 0
    top10_hp = 0
    
    with open(args.candidates, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip(): continue
            c = json.loads(line)
            cid = c.get('candidate_id', '')
            if cid not in sub_ids:
                continue
            
            rank = sub_ids.index(cid) + 1
            profile = c.get('profile', {})
            skills = c.get('skills', [])
            career_history = c.get('career_history', [])
            signals = c.get('redrob_signals', {})
            
            yoe = float(profile.get('years_of_experience', 0.0))
            
            # H1: Total tenure exceeds experience
            total_tenure = sum(j.get('duration_months', 0) for j in career_history)
            h1 = total_tenure > (yoe * 12) + 6
            
            # H2: Single skill duration exceeds experience
            h2 = any(s.get('duration_months', 0) > (yoe * 12) + 12 for s in skills)
            
            # H3: 8+ expert skills with <6 months each
            h3 = sum(1 for s in skills if s.get('proficiency', '') == 'expert' and s.get('duration_months', 0) < 6) >= 8
            
            # H4: Open to work but inactive >90 days
            h4 = bool(signals.get('open_to_work_flag', False)) and signals.get('last_active_date', max_date) < stale_threshold
            
            # H5: Manager/Director with no GitHub activity
            current_title = profile.get('current_title', '').lower()
            gh_score = int(signals.get('github_activity_score', -1))
            h5 = ('manager' in current_title or 'director' in current_title) and gh_score < 5
            
            fires = [('H1', h1), ('H2', h2), ('H3', h3), ('H4', h4), ('H5', h5)]
            any_fire = any(f[1] for f in fires)
            
            if any_fire:
                total_hp += 1
                if rank <= 10:
                    top10_hp += 1
                fired = [f[0] for f in fires if f[1]]
                print(f"Rank {rank} ({cid}) FIRED: {', '.join(fired)}")
    
    print(f"\nTotal honeypots in top 100: {total_hp}")
    print(f"Total honeypots in top 10: {top10_hp}")
    print(f"Result: {'PASS' if total_hp <= 10 else 'FAIL - DISQUALIFIED'}")

if __name__ == '__main__':
    main()