# In run_editor.py

from src.editor_app import create_app

# --- FIX: Renamed function call to match the actual function name ---
app = create_app()

if __name__ == "__main__":
    # Note: debug=True is not recommended for production.
    app.run(debug=True, port=5001)
