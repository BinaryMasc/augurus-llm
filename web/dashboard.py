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

    @app.route('/api/session/<int:session_id>/candles')
    def api_session_candles(session_id):
        session = db.get_session_by_id(session_id)
        if session is None:
            return jsonify({'error': 'Session not found'}), 404

        csv_file = session.get('csv_file')
        # Allow passing timeframe as query parameter, default to session's trading timeframe
        timeframe = request.args.get('timeframe', session.get('trading_timeframe', 'M1')).upper()
        last_ts = session.get('last_candle_timestamp')

        try:
            import pandas as pd
            from engine.data_feed import DataFeed
            data_feed = DataFeed(csv_file, timeframe)
            
            if last_ts:
                # Slice candles up to the simulation checkpoint timestamp
                df_slice = data_feed.df[data_feed.df['datetime'] <= pd.to_datetime(last_ts)].copy()
            else:
                candles_to_pass = session.get('candles_to_pass', 15)
                limit = min(candles_to_pass, len(data_feed.df))
                df_slice = data_feed.df.iloc[0:limit].copy()

            df_slice['time'] = df_slice['datetime'].dt.tz_localize('UTC').apply(lambda x: int(x.timestamp()))
            
            candles = df_slice[['time', 'open', 'high', 'low', 'close', 'volume']].to_dict(orient='records')
            return jsonify({
                'candles': candles,
                'last_candle_index': session.get('last_candle_index', 0),
                'last_candle_timestamp': last_ts
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    return app


def run_dashboard(db_path: str, host: str = '0.0.0.0', port: int = 8080):
    db = Database(db_path)
    app = create_app(db)
    print(f"[*] Augurus Dashboard starting on http://{host}:{port}")
    app.run(host=host, port=port, debug=False)
