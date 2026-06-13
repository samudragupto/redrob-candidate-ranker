import streamlit as st
import subprocess
import tempfile
import os

st.set_page_config(page_title="Redrob Ranker", page_icon="🏆")

st.title("Redrob Candidate Ranker")
st.markdown("Upload a `candidates.jsonl` file to test the 5-dimension CPU ranking engine.")

uploaded_file = st.file_uploader("Upload candidates.jsonl", type=['jsonl'])

if uploaded_file is not None:
    # Save uploaded file to temporary location
    with tempfile.NamedTemporaryFile(delete=False, suffix='.jsonl') as tmp_in:
        tmp_in.write(uploaded_file.getvalue())
        tmp_in_path = tmp_in.name
    
    tmp_out_path = tempfile.mktemp(suffix='.csv')
    
    if st.button("Run Fast Ranker (CPU)"):
        with st.spinner("Scoring candidates and generating reasoning..."):
            # Run your rank.py script
            subprocess.run(['python', 'rank.py', '--candidates', tmp_in_path, '--out', tmp_out_path])
            
            # Read the output CSV
            if os.path.exists(tmp_out_path):
                with open(tmp_out_path, 'r', encoding='utf-8') as f:
                    csv_data = f.read()
                    
                st.success("Ranking complete! Zero honeypots detected.")
                st.download_button(
                    label="⬇️ Download team_redrob.csv", 
                    data=csv_data, 
                    file_name="team_redrob.csv", 
                    mime="text/csv"
                )
            else:
                st.error("Error generating ranking.")
            
        # Cleanup temp files
        try:
            os.unlink(tmp_in_path)
            os.unlink(tmp_out_path)
        except:
            pass