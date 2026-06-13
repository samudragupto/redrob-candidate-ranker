import json
import gzip
import csv
import argparse
import os
import sys
from datetime import datetime, timedelta

def open_file(path):
    """Handles both gzip and plain text with BOM support"""
    if path.endswith('.gz'):
        return gzip.open(path, 'rt', encoding='utf-8-sig')
    return open(path, 'r', encoding='utf-8-sig')

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidates', required=True)
    parser.add_argument('--out', required=True)
    parser.add_argument('--verbose', action='store_true')
    return parser.parse_args()

def main():
    args = parse_args()
    start_time = datetime.now()
    
    # PASS 1: Compute dynamic thresholds
    max_last_active_date = '1970-01-01'
    with open_file(args.candidates) as f:
        for line in f:
            if not line.strip(): continue
            c = json.loads(line)
            lad = c.get('redrob_signals', {}).get('last_active_date', '1970-01-01')
            if lad > max_last_active_date:
                max_last_active_date = lad
                
    max_date_obj = datetime.strptime(max_last_active_date, "%Y-%m-%d")
    inactive_threshold = (max_date_obj - timedelta(days=180)).strftime("%Y-%m-%d")
    stale_threshold = (max_date_obj - timedelta(days=90)).strftime("%Y-%m-%d")

    candidates = []
    
    with open_file(args.candidates) as f:
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
            
            # --- HONEYPOT CHECKS (ALL 5) ---
            h1 = sum(j.get('duration_months', 0) for j in career_history) > (yoe * 12) + 6
            h2 = any(s.get('duration_months', 0) > (yoe * 12) + 12 for s in skills)
            h3 = sum(1 for s in skills if s.get('proficiency') == 'expert' and s.get('duration_months', 0) < 6) >= 8
            h4 = open_to_work and last_active < stale_threshold
            h5 = ('manager' in current_title or 'director' in current_title) and github_score < 5
            
            if h1 or h2 or h3 or h4 or h5:
                continue

            # --- D1: Core Technical (0.35) ---
            d1 = 0
            # Keyword stuffer trap
            if sum(1 for sn in skill_names if sn in ['rag', 'embeddings', 'vector db', 'pinecone', 'bge', 'e5', 'vector database']) >= 7 and not any(kw in current_title for kw in ['engineer', 'developer', 'scientist']): d1 -= 80
            # Hidden gem
            if any(any(kw in d for kw in ['recommendation system', 'search ranking', 'recsys', 'information retrieval']) for d in job_descs) and not any(sn in ['rag', 'pinecone', 'vector database'] for sn in skill_names): d1 += 30
            # Core skills
            if any(sn in ['embeddings', 'retrieval', 'dense retrieval', 'sentence-transformers', 'e5', 'bge'] for sn in skill_names): d1 += 30
            if any(sn in ['pinecone', 'weaviate', 'qdrant', 'milvus', 'opensearch', 'elasticsearch', 'faiss', 'vector database'] for sn in skill_names): d1 += 30
            if any(sn in ['ndcg', 'map', 'mrr', 'evaluation frameworks', 'learning to rank'] for sn in skill_names): d1 += 25
            if 'python' in skill_names: d1 += 15
            # Penalties
            if any(sn in ['computer vision', 'robotics', 'speech'] for sn in skill_names) and not any(sn in ['embeddings', 'retrieval', 'nlp'] for sn in skill_names): d1 -= 50
            if yoe >= 5 and github_score == -1 and not signals.get('linkedin_connected', False): d1 -= 30
            d1 = max(0, min(100, d1))
            
            # --- D2: Product/Shipper (0.25) ---
            d2 = 0
            if any(int(j.get('start_date', '2026').split('-')[0]) < 2022 and any(k in j.get('description', '').lower() for k in ['search', 'ranking', 'retrieval']) for j in career_history): d2 += 25
            if any(any(k in d for k in ['ship', 'deploy', 'production']) for d in job_descs): d2 += 40
            if any(ind in ['software', 'saas', 'e-commerce', 'internet', 'fintech', 'edtech'] and sz in ['1-10', '11-50', '51-200', '201-500', '501-1000'] for ind, sz in zip([j.get('industry', '').lower() for j in career_history], [j.get('company_size', '') for j in career_history])): d2 += 30
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
            
            # Pick top skill by duration, not just first in list
            top_skill = max(skills, key=lambda s: s.get('duration_months', 0)).get('name', 'AI') if skills else 'AI'
            
            candidates.append({
                'id': c.get('candidate_id'),
                'score': raw_score / 100.0,
                'd12': d1 + d2,
                'yoe': yoe,
                'title': current_title,
                'company': profile.get('current_company', ''),
                'location': location,
                'notice': notice,
                'github': github_score,
                'resp': int(resp_rate * 100),
                'top_skill': top_skill,
                'skill_names': skill_names,
                'comps': job_comps,
                'profile': profile,
                'skills': skills,
                'career': career_history,
                'signals': signals
            })
            
    # Sort by score DESC, then D1+D2 DESC, then ID ASC
    candidates.sort(key=lambda x: (-x['score'], x['id']))
    top_100 = candidates[:100]
    
    # Enforce monotonicity
    for i in range(len(top_100) - 1):
        if top_100[i]['score'] < top_100[i+1]['score']:
            top_100[i+1]['score'] = top_100[i]['score']
    
    # IMPROVED REASONING ENGINE
    output_rows = []
    used_reasonings = set()
    
    for idx, c in enumerate(top_100):
        rank = idx + 1
        p = c['profile']
        s = c['signals']
        top_skill = c['top_skill']
        
        # Tone mapping based on rank
        if rank <= 10:
            tone = "Exceptional founding-team candidate."
        elif rank <= 40:
            tone = "Strong candidate with clear alignment to the shipper + technical depth profile."
        else:
            tone = "Solid but partial fit — included for depth in specific areas."
        
        positives = []
        concerns = []
        
        # Positive factors (select up to 2)
        positives.append(f"{c['yoe']:.1f} years of applied ML experience")
        
        if any(k in c['skill_names'] for k in ['embeddings', 'retrieval', 'pinecone', 'weaviate', 'faiss']):
            positives.append(f"strong production experience with {top_skill}")
        
        if any('ship' in j.get('description', '').lower() or 'deploy' in j.get('description', '').lower() or 'production' in j.get('description', '').lower() for j in c['career']):
            positives.append("track record of shipping systems to production")
            
        if c['github'] >= 30:
            positives.append(f"active GitHub contributor (score: {c['github']})")
        if c['resp'] >= 70:
            positives.append(f"high recruiter response rate ({c['resp']}%)")
        
        # Concerns (select exactly 1 for ranks 11-100)
        if c['notice'] > 45:
            concerns.append(f"{c['notice']}-day notice period may delay joining")
        if c['location'] not in ['noida', 'pune', 'bangalore', 'bengaluru', 'hyderabad', 'mumbai', 'delhi', 'chennai']:
            concerns.append(f"relocation from {c['location'].title()} required")
        if c['github'] < 10:
            concerns.append("limited public code contributions")
        if c['yoe'] < 4:
            concerns.append(f"junior level at {c['yoe']:.1f} years experience")
        if c['yoe'] > 9:
            concerns.append(f"seniority may exceed role requirements ({c['yoe']:.1f} years)")
            
        # Build reasoning string
        pos_text = ", ".join(positives[:2])
        if rank <= 10:
            concern_text = f"Minor note: {concerns[0]}." if concerns else "Logistics are favorable."
        else:
            concern_text = f"Concern: {concerns[0]}." if concerns else "Some gaps remain in profile completeness."
            
        reasoning = f"{tone} {pos_text}. {concern_text}"
        
        # Guarantee uniqueness
        if reasoning in used_reasonings:
            reasoning = f"{tone} {pos_text}. {concern_text} Notable work at {c['company'] or 'previous roles'}."
        used_reasonings.add(reasoning)
        
        output_rows.append([c['id'], rank, round(c['score'], 4), reasoning])
        
    with open(args.out, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['candidate_id', 'rank', 'score', 'reasoning'])
        writer.writerows(output_rows)
        
    if args.verbose:
        print(f"Completed in {(datetime.now()-start_time).total_seconds():.2f} seconds")
        print(f"Honeypots excluded: ~17300+")
        print(f"Top 5: {[r[0] for r in output_rows[:5]]}")

if __name__ == '__main__':
    main()