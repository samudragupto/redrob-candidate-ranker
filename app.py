import streamlit as st
import subprocess
import tempfile
import os
import sys

st.set_page_config(page_title="Redrob Ranker", layout="wide")
st.title("🚀 Redrob Candidate Ranking Engine")
st.write("Upload a `.jsonl` or `.jsonl.gz` file to test the 5-dimension CPU ranking engine.")

# Increase upload limit for this session
st.config.set_option('server.maxUploadSize', 500)

uploaded_file = st.file_uploader("Upload candidates file", type=['jsonl', 'gz', 'json'])

if uploaded_file is not None:
    if st.button("Run Ranking Engine"):
        with st.spinner("Processing candidates..."):
            # Use NamedTemporaryFile for safe Docker permissions
            with tempfile.NamedTemporaryFile(delete=False, suffix='.jsonl') as tmp_in:
                tmp_in.write(uploaded_file.getvalue())
                tmp_in_path = tmp_in.name
            
            with tempfile.NamedTemporaryFile(delete=False, suffix='.csv') as tmp_out:
                tmp_out_path = tmp_out.name
            
            # CRITICAL FIX: Use sys.executable instead of 'python' for Docker environments
            result = subprocess.run(
                [sys.executable, 'rank.py', '--candidates', tmp_in_path, '--out', tmp_out_path],
                capture_output=True, text=True
            )
            
            # Check if it succeeded
            if result.returncode == 0 and os.path.exists(tmp_out_path) and os.path.getsize(tmp_out_path) > 0:
                with open(tmp_out_path, 'r') as f:
                    csv_data = f.read()
                st.success("Ranking complete! Honeypots excluded. Monotonicity enforced.")
                st.download_button("Download submission.csv", csv_data, "submission.csv", "text/csv")
            else:
                st.error("Error generating ranking. See debug logs below:")
                st.text("STDOUT:")
                st.code(result.stdout)
                st.text("STDERR (The actual error):")
                st.code(result.stderr)
            
            # Cleanup
            if os.path.exists(tmp_in_path): os.unlink(tmp_in_path)
            if os.path.exists(tmp_out_path): os.unlink(tmp_out_path)