import csv
import json
import argparse
from collections import Counter

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--submission', required=True)
    parser.add_argument('--candidates', required=True)
    args = parser.parse_args()
    
    # Load submission
    sub_data = []
    with open(args.submission, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            sub_data.append(row)
    
    sub_ids = {r['candidate_id'] for r in sub_data}
    
    # Load matching candidates
    cand_lookup = {}
    with open(args.candidates, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip(): continue
            c = json.loads(line)
            if c.get('candidate_id') in sub_ids:
                cand_lookup[c.get('candidate_id')] = c
    
    # Analyze
    locs = Counter()
    yoe_bins = Counter()
    skills_counter = Counter()
    companies_counter = Counter()
    resp_sum = 0.0
    open_count = 0
    reasonings = set()
    r_lengths = []
    
    for row in sub_data:
        c = cand_lookup.get(row['candidate_id'], {})
        profile = c.get('profile', {})
        skills = c.get('skills', [])
        signals = c.get('redrob_signals', {})
        
        loc = profile.get('location', 'Unknown')
        if loc == 'N/A' or not loc:
            loc = 'Unknown'
        locs[loc] += 1
        
        yoe = float(profile.get('years_of_experience', 0))
        if yoe <= 3: yoe_bins['0-3'] += 1
        elif yoe <= 5: yoe_bins['3-5'] += 1
        elif yoe <= 7: yoe_bins['5-7'] += 1
        elif yoe <= 9: yoe_bins['7-9'] += 1
        elif yoe <= 12: yoe_bins['9-12'] += 1
        else: yoe_bins['12+'] += 1
        
        for s in skills:
            skills_counter[s.get('name', 'Unknown')] += 1
        
        comp = profile.get('current_company', 'Unknown')
        if comp and comp != 'N/A':
            companies_counter[comp] += 1
        
        resp_sum += float(signals.get('recruiter_response_rate', 0.0))
        if signals.get('open_to_work_flag', False):
            open_count += 1
        
        reasonings.add(row['reasoning'])
        r_lengths.append(len(row['reasoning']))
    
    print("=" * 60)
    print("DIVERSITY CHECK REPORT")
    print("=" * 60)
    print(f"\nLocation Distribution:")
    for loc, count in locs.most_common(10):
        print(f"  {loc}: {count}")
    
    print(f"\nYears of Experience:")
    for k in ['0-3', '3-5', '5-7', '7-9', '9-12', '12+']:
        if k in yoe_bins:
            print(f"  {k}: {yoe_bins[k]}")
    
    print(f"\nTop 15 Skills:")
    for skill, count in skills_counter.most_common(15):
        print(f"  {skill}: {count}")
    
    print(f"\nTop 10 Companies:")
    for comp, count in companies_counter.most_common(10):
        print(f"  {comp}: {count}")
    
    print(f"\nBehavioral Metrics:")
    print(f"  Avg Response Rate: {resp_sum/100:.2f}")
    print(f"  Open to Work: {open_count}/100")
    
    print(f"\nReasoning Quality:")
    print(f"  Unique Reasonings: {len(reasonings)}/100")
    print(f"  Min Length: {min(r_lengths)} chars")
    print(f"  Max Length: {max(r_lengths)} chars")
    print(f"  Avg Length: {sum(r_lengths)/100:.1f} chars")
    
    print(f"\n--- TOP 10 DEEP DIVE ---")
    for i in range(min(10, len(sub_data))):
        row = sub_data[i]
        c = cand_lookup.get(row['candidate_id'], {})
        profile = c.get('profile', {})
        skills = c.get('skills', [])
        signals = c.get('redrob_signals', {})
        
        top3 = [s.get('name', '') for s in skills[:3]]
        print(f"\nRank {row['rank']}: {row['candidate_id']}")
        print(f"  Score: {row['score']}")
        print(f"  Profile: {profile.get('years_of_experience', '?')}yrs | {profile.get('location', '?')} | {profile.get('current_title', '?')}")
        print(f"  Company: {profile.get('current_company', '?')}")
        print(f"  Top Skills: {', '.join(top3)}")
        print(f"  Response Rate: {signals.get('recruiter_response_rate', 0):.2f}")
        print(f"  GitHub Score: {signals.get('github_activity_score', -1)}")
        print(f"  Reasoning: {row['reasoning'][:150]}...")

if __name__ == '__main__':
    main()