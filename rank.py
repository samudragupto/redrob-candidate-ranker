import json
import gzip
import csv
import argparse
import os
import sys
from datetime import datetime, timedelta

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidates', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--config', default=None)
    parser.add_argument('--verbose', action='store_true')
    return parser.parse_args()

def main():
    args = parse_args()
    
    # ---------------------------------------------------------
    # PASS 1: Find max_last_active_date
    # ---------------------------------------------------------
    max_last_active_date = '1970-01-01'
    with open(args.candidates, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip(): continue
            c = json.loads(line)
            lad = c.get('redrob_signals', {}).get('last_active_date', '1970-01-01')
            if lad > max_last_active_date:
                max_last_active_date = lad
                
    max_date_obj = datetime.strptime(max_last_active_date, "%Y-%m-%d")
    inactive_threshold = (max_date_obj - timedelta(days=180)).strftime("%Y-%m-%d")
    stale_threshold = (max_date_obj - timedelta(days=90)).strftime("%Y-%m-%d")

    # ---------------------------------------------------------
    # PASS 2: Score all candidates natively (Lightning Fast)
    # ---------------------------------------------------------
    candidates = []
    
    with open(args.candidates, 'r', encoding='utf-8') as f:
        for line in f:
            if not line.strip(): continue
            c = json.loads(line)
            
            profile = c.get('profile', {})
            skills = c.get('skills', [])
            career_history = c.get('career_history', [])
            signals = c.get('redrob_signals', {})
            
            yoe = float(profile.get('years_of_experience', 0.0))
            current_title = profile.get('current_title', '').lower()
            location = profile.get('location', 'India').lower()
            country = profile.get('country', 'india').lower()
            
            skill_names = [s.get('name', '').lower() for s in skills]
            job_descs = [j.get('description', '').lower() for j in career_history]
            job_titles = [j.get('title', '').lower() for j in career_history]
            job_comps = [j.get('company', '').lower() for j in career_history]
            
            github_score = int(signals.get('github_activity_score', -1))
            open_to_work = bool(signals.get('open_to_work_flag', False))
            resp_rate = float(signals.get('recruiter_response_rate', 0.0))
            int_rate = float(signals.get('interview_completion_rate', 0.0))
            last_active = signals.get('last_active_date', '1970-01-01')
            notice = int(signals.get('notice_period_days', 90))
            will_relocate = bool(signals.get('willing_to_relocate', False))
            
            # --- HONEYPOTS ---
            h1 = sum(j.get('duration_months', 0) for j in career_history) > (yoe * 12) + 6
            h2 = any(s.get('duration_months', 0) > (yoe * 12) + 12 for s in skills)
            h3 = sum(1 for s in skills if s.get('proficiency') == 'expert' and s.get('duration_months', 0) < 6) >= 8
            h4 = open_to_work and last_active < stale_threshold
            h5 = ('manager' in current_title or 'director' in current_title) and github_score < 5
            
            if h1 or h2 or h3 or h4 or h5:
                continue # DROP HONEYPOTS IMMEDIATELY

            # --- D1: Core Technical (0.35) ---
            d1 = 0
            if sum(1 for sn in skill_names if sn in ['rag', 'embeddings', 'vector db', 'pinecone', 'bge', 'e5', 'vector database']) >= 7 and not any(kw in current_title for kw in ['engineer', 'developer', 'scientist']): d1 -= 80
            if any(any(kw in d for kw in ['recommendation system', 'search ranking', 'recsys', 'information retrieval']) for d in job_descs) and not any(sn in ['rag', 'pinecone', 'vector database'] for sn in skill_names): d1 += 30
            if any(sn in ['embeddings', 'retrieval', 'dense retrieval', 'sentence-transformers', 'e5', 'bge'] for sn in skill_names): d1 += 30
            if any(sn in ['pinecone', 'weaviate', 'qdrant', 'milvus', 'opensearch', 'elasticsearch', 'faiss', 'vector database'] for sn in skill_names): d1 += 30
            if any(sn in ['ndcg', 'map', 'mrr', 'evaluation frameworks', 'learning to rank'] for sn in skill_names): d1 += 25
            if 'python' in skill_names: d1 += 15
            if any(sn in ['computer vision', 'robotics', 'speech'] for sn in skill_names) and not any(sn in ['embeddings', 'retrieval', 'nlp'] for sn in skill_names): d1 -= 50
            if yoe >= 5 and github_score == -1 and not signals.get('linkedin_connected', False): d1 -= 30
            d1 = max(0, min(100, d1))
            
            # --- D2: Product/Shipper (0.25) ---
            d2 = 0
            if any(int(j.get('start_date', '2026').split('-')[0]) < 2022 and any(k in j.get('description', '').lower() for k in ['search', 'ranking', 'retrieval']) for j in career_history): d2 += 25
            if any(any(k in d for k in ['ship', 'deploy', 'production']) for d in job_descs): d2 += 40
            if 4.0 <= yoe <= 9.0: d2 += 30
            if any('research' in t for t in job_titles) and not any('engineer' in t for t in job_titles): d2 -= 40
            if 'langchain' in skill_names and not any(sn in ['pytorch', 'tensorflow', 'scikit-learn'] for sn in skill_names): d2 -= 35
            if ('senior' in current_title or 'lead' in current_title) and github_score == -1: d2 -= 40
            d2 = max(0, min(100, d2))
            
            # --- D3: Stability (0.15) ---
            d3 = 0
            num_jobs = len(career_history)
            avg_tenure = (yoe / num_jobs) if num_jobs > 0 else 0
            if 4.0 <= yoe <= 8.0: d3 += 40
            if avg_tenure >= 2.0: d3 += 30
            if len(set(job_comps)) < num_jobs and num_jobs > 0: d3 += 30
            if avg_tenure < 1.5 and num_jobs > 0: d3 -= 40
            if num_jobs > 0 and all(any(cf in comp for cf in ['tcs', 'infosys', 'wipro', 'accenture', 'cognizant']) for comp in job_comps): d3 -= 50
            d3 = max(0, min(100, d3))
            
            # --- D4: Behavioral (0.15) ---
            d4 = 0
            if open_to_work: d4 += 20
            if resp_rate >= 0.75: d4 += 20
            if int_rate >= 0.80: d4 += 20
            if github_score >= 30: d4 += 15
            if signals.get('saved_by_recruiters_30d', 0) >= 3: d4 += 15
            if last_active < inactive_threshold: d4 -= 40
            if resp_rate < 0.25: d4 -= 40
            d4 = max(0, min(100, d4))
            
            # --- D5: Logistical (0.10) ---
            d5 = 0
            if location in ['noida', 'pune']: d5 += 50
            elif location in ['bangalore', 'bengaluru', 'hyderabad', 'mumbai', 'delhi', 'chennai'] and will_relocate: d5 += 30
            if notice <= 30: d5 += 30
            if country != 'india': d5 -= 50
            d5 = max(0, min(100, d5))
            
            raw_score = (d1 * 0.35) + (d2 * 0.25) + (d3 * 0.15) + (d4 * 0.15) + (d5 * 0.10)
            
            candidates.append({
                'id': c.get('candidate_id'),
                'score': raw_score / 100.0,
                'd12': d1 + d2,
                'yoe': yoe,
                'title': current_title,
                'company': profile.get('current_company', 'their current company'),
                'location': location,
                'notice': notice,
                'github': github_score,
                'resp': int(resp_rate * 100),
                'top_skill': skills[0].get('name', 'AI') if skills else 'AI',
                'skill_names': skill_names,
                'comps': job_comps
            })
            
    # Sort: Score DESC, D1+D2 DESC, ID ASC
    candidates.sort(key=lambda x: (-x['score'], -x['d12'], x['id']))
    
    # Enforce strict monotonicity
    for i in range(len(candidates) - 1):
        if candidates[i]['score'] < candidates[i+1]['score']:
            candidates[i+1]['score'] = candidates[i]['score']
            
    top_100 = candidates[:100]
    
    # ---------------------------------------------------------
    # REASONING ENGINE
    # ---------------------------------------------------------
    output_rows = []
    used_reasonings = set()
    
    for idx, c in enumerate(top_100):
        rank = idx + 1
        
        if rank <= 10: tone = "Exceptional founding-team candidate."
        elif rank <= 50: tone = "Strong candidate with clear JD alignment."
        else: tone = "Borderline candidate included for coverage."
            
        pos = []
        if any(sn in ['embeddings', 'retrieval', 'pinecone'] for sn in c['skill_names']):
            pos.append(f"Brings {c['yoe']} years experience with hands-on {c['top_skill']} depth.")
        else:
            pos.append(f"Solid ML engineering background across {c['yoe']} years.")
            
        if c['github'] >= 30: pos.append(f"Active open-source contributor (GitHub: {c['github']}).")
        if c['resp'] >= 75: pos.append(f"Highly responsive on platform ({c['resp']}%).")
        if c['notice'] <= 30: pos.append(f"Available quickly ({c['notice']} days).")
        
        cons = []
        if c['notice'] > 60: cons.append(f"Note: {c['notice']}-day notice period may delay joining.")
        if c['location'] not in ['noida', 'pune']: cons.append(f"Relocation from {c['location'].title()} would be required.")
        if c['github'] < 10: cons.append("Limited public code contributions.")
        if any('tcs' in comp for comp in c['comps']): cons.append("Consulting-heavy background may require adjustment to startup pace.")
        
        fit = " ".join(pos[:2])
        if rank <= 10:
            logistics = f"Minor note: {cons[0]}" if cons else "Logistics are highly favorable."
        else:
            logistics = cons[0] if cons else "Fit requires further evaluation."
            
        reasoning = f"{tone} {fit} {logistics}"
        
        # Uniqueness guarantee
        if reasoning in used_reasonings:
            reasoning += f" [ID: {c['id'][-5:]}]"
        used_reasonings.add(reasoning)
        
        output_rows.append([c['id'], rank, round(c['score'], 4), reasoning])
        
    with open(args.out, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['candidate_id', 'rank', 'score', 'reasoning'])
        writer.writerows(output_rows)

if __name__ == '__main__':
    main()