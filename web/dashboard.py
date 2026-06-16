from flask import Flask, jsonify, render_template, request
from database.db import Database


def create_app(db: Database):
    app = Flask(__name__)

    @app.route('/')
    def index():
        sessions = db.get_sessions_list()
        return render_template('index.html', sessions=sessions)

    @app.route('/session/<int:session_id>')
    def session_detail(session_id):
        stats = db.get_session_details(session_id)
        if stats is None:
            return "Session not found", 404
        return render_template('session.html', sid=session_id, stats=stats)

    @app.route('/api/sessions')
    def api_sessions():
        sessions = db.get_sessions_list()
        return jsonify(sessions)

    @app.route('/api/session/<int:session_id>/stats')
    def api_session_stats(session_id):
        stats = db.get_session_details(session_id)
        if stats is None:
            return jsonify({'error': 'Session not found'}), 404
        return jsonify(stats)

    return app


def run_dashboard(db_path: str, host: str = '0.0.0.0', port: int = 8080):
    db = Database(db_path)
    app = create_app(db)
    print(f"[*] Augurus Dashboard starting on http://{host}:{port}")
    app.run(host=host, port=port, debug=False)
