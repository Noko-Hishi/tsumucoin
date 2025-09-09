# -*- coding: utf-8 -*-
import streamlit as st
import json
import math
import os
import requests
import pandas as pd
from io import StringIO
from datetime import datetime
import base64

# 設定
DATA_FILE = "coin_data_multi.json"
COIN_MULTIPLIERS = [1.1, 1.3, 1.5, 2, 2.5, 3, 4, 5, 6, 11, 21, 51]

def snap_rate_to_multiplier(rate: float) -> float:
    """倍率を最も近いCOIN_MULTIPLIERSの値にスナップする"""
    if rate <= 0 or math.isnan(rate) or math.isinf(rate):
        return rate
    return min(COIN_MULTIPLIERS, key=lambda m: abs(m - rate))

def get_config_value(key, fallback_key=None, default_value=""):
    """設定値を取得（Secrets > セッション状態 > デフォルト値の順）"""
    # まずSecretsから取得を試行
    try:
        if key in st.secrets:
            return st.secrets[key]
        if fallback_key and fallback_key in st.secrets:
            return st.secrets[fallback_key]
    except Exception:
        pass
    
    # セッション状態から取得
    if key in st.session_state:
        return st.session_state[key]
    if fallback_key and fallback_key in st.session_state:
        return st.session_state[fallback_key]
    
    return default_value

def get_github_file(token, owner, repo, path, branch="main"):
    """GitHubからファイルを取得"""
    if not token:
        return None, "GitHubトークンが設定されていません"
    
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            file_data = response.json()
            content = base64.b64decode(file_data['content']).decode('utf-8')
            return json.loads(content), None
        elif response.status_code == 404:
            # ファイルが存在しない場合は空のデータを返す
            return {}, None
        else:
            return None, f"GitHub API エラー: {response.status_code}"
    except Exception as e:
        return None, f"エラー: {str(e)}"

def save_to_github(token, owner, repo, path, data, message="Update coin data", branch="main"):
    """GitHubにファイルを保存"""
    if not token:
        return False, "GitHubトークンが設定されていません"
    
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    try:
        # まず既存ファイルのSHAを取得
        response = requests.get(url, headers=headers)
        sha = None
        if response.status_code == 200:
            sha = response.json()['sha']
        
        # ファイル内容をBase64エンコード
        content = json.dumps(data, ensure_ascii=False, indent=2)
        content_b64 = base64.b64encode(content.encode('utf-8')).decode('utf-8')
        
        # ファイルを更新/作成
        payload = {
            "message": message,
            "content": content_b64,
            "branch": branch
        }
        
        if sha:
            payload["sha"] = sha
        
        response = requests.put(url, json=payload, headers=headers)
        
        if response.status_code in [200, 201]:
            return True, "✅ GitHubに保存成功"
        else:
            return False, f"❌ GitHub保存失敗: {response.status_code} - {response.text}"
    except Exception as e:
        return False, f"❌ エラー: {str(e)}"

def send_to_discord(webhook_url, tsum_name, record, use_5to4=False, use_plus_coin=False):
    """Discord Webhookに記録を送信"""
    if not webhook_url:
        return False, "Webhook URLが設定されていません"
    
    # アイテム情報
    items_used = []
    if use_5to4:
        items_used.append("5→4")
    if use_plus_coin:
        items_used.append("+Coin")
    
    items_text = f" (アイテム: {', '.join(items_used)})" if items_used else ""
    
    # 埋め込みメッセージを作成
    embed = {
        "title": "🪙 ツムツム コイン記録",
        "color": 0x00ff00,  # 緑色
        "timestamp": datetime.now().isoformat(),
        "fields": [
            {
                "name": "🎯 ツム",
                "value": tsum_name,
                "inline": True
            },
            {
                "name": "💰 ベースコイン",
                "value": f"{record['base']:,}",
                "inline": True
            },
            {
                "name": "🚀 最終コイン",
                "value": f"{record['boost']:,}",
                "inline": True
            },
            {
                "name": "📈 倍率",
                "value": f"**{record['rate']}x**",
                "inline": True
            },
            {
                "name": "💎 実質獲得",
                "value": f"{record['final']:,}",
                "inline": True
            },
            {
                "name": "⚡ アイテム",
                "value": items_text if items_text else "なし",
                "inline": True
            }
        ],
        "footer": {
            "text": "ツムツム コイン記録ツール"
        }
    }
    
    # Webhook送信データ
    data = {
        "username": "ツムツム記録Bot",
        "embeds": [embed]
    }
    
    try:
        response = requests.post(webhook_url, json=data)
        if response.status_code == 204:
            return True, "✅ Discordに送信成功"
        else:
            return False, f"❌ 送信失敗: {response.status_code}"
    except Exception as e:
        return False, f"❌ エラー: {str(e)}"

def send_json_to_discord(webhook_url, json_data, filename="coin_data_multi.json"):
    """Discord WebhookにJSONファイルを添付ファイルとして送信"""
    if not webhook_url:
        return False, "Webhook URLが設定されていません"
    
    try:
        # JSONデータを文字列に変換
        json_string = json.dumps(json_data, ensure_ascii=False, indent=2)
        json_bytes = json_string.encode('utf-8')
        
        # 統計情報を計算
        total_tsums = len(json_data)
        total_records = sum(len(records) for records in json_data.values())
        
        # 埋め込みメッセージ
        embed = {
            "title": "📄 ツムツム データバックアップ",
            "description": f"**{filename}** をアップロードしました",
            "color": 0x0099ff,  # 青色
            "timestamp": datetime.now().isoformat(),
            "fields": [
                {
                    "name": "📊 統計情報",
                    "value": f"🎯 ツム数: **{total_tsums}**\n📝 総記録数: **{total_records}**",
                    "inline": False
                }
            ],
            "footer": {
                "text": "ツムツム コイン記録ツール - データバックアップ"
            }
        }
        
        # マルチパートフォームデータを作成
        files = {
            'file': (filename, json_bytes, 'application/json')
        }
        
        payload = {
            'username': 'ツムツム記録Bot',
            'embeds': [embed]
        }
        
        response = requests.post(webhook_url, data={'payload_json': json.dumps(payload)}, files=files)
        
        if response.status_code == 200:
            return True, f"✅ JSONファイル ({filename}) をDiscordに送信成功"
        else:
            return False, f"❌ 送信失敗: {response.status_code}"
            
    except Exception as e:
        return False, f"❌ エラー: {str(e)}"

def load_existing_data():
    """既存のデータを読み込む（GitHub優先、次にセッション状態）"""
    if 'coin_data' not in st.session_state:
        # GitHub設定を取得（Secrets優先）
        github_token = get_config_value('github_token', 'GITHUB_TOKEN')
        github_owner = get_config_value('github_owner', 'GITHUB_OWNER')
        github_repo = get_config_value('github_repo', 'GITHUB_REPO')
        github_path = get_config_value('github_path', 'GITHUB_PATH', DATA_FILE)
        
        if github_token and github_owner and github_repo:
            # GitHubからデータを読み込み
            data, error = get_github_file(github_token, github_owner, github_repo, github_path)
            if error:
                st.warning(f"GitHub読み込みエラー: {error}")
                st.session_state.coin_data = {}
            else:
                st.session_state.coin_data = data
                if data:
                    st.success(f"✅ GitHubからデータを読み込みました ({len(data)} ツム)")
        else:
            # ローカルファイルを試行（後方互換性）
            if os.path.exists(DATA_FILE):
                try:
                    with open(DATA_FILE, 'r', encoding='utf-8') as f:
                        st.session_state.coin_data = json.load(f)
                    st.info(f"✅ ローカルファイル ({DATA_FILE}) を読み込みました")
                except Exception as e:
                    st.warning(f"ローカルファイル読み込みエラー: {e}")
                    st.session_state.coin_data = {}
            else:
                st.session_state.coin_data = {}
    return st.session_state.coin_data

def save_data_to_session(data):
    """データをセッション状態とGitHub/ローカルファイルに保存"""
    st.session_state.coin_data = data
    
    # GitHub設定を取得（Secrets優先）
    github_token = get_config_value('github_token', 'GITHUB_TOKEN')
    github_owner = get_config_value('github_owner', 'GITHUB_OWNER')
    github_repo = get_config_value('github_repo', 'GITHUB_REPO')
    github_path = get_config_value('github_path', 'GITHUB_PATH', DATA_FILE)
    
    if github_token and github_owner and github_repo:
        # GitHubに保存
        success, message = save_to_github(github_token, github_owner, github_repo, github_path, data)
        if success:
            st.session_state.last_github_save = "成功"
        else:
            st.session_state.last_github_save = f"失敗: {message}"
            # GitHub保存に失敗した場合はローカルファイルにも保存
            save_data_to_file(data)
    else:
        # ローカルファイルに保存
        save_data_to_file(data)

def save_data_to_file(data):
    """データをJSONファイルに保存"""
    try:
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        st.error(f"ファイル保存エラー: {e}")
        return False

def calculate_record(base_coin, boost_coin, use_5to4, use_plus_coin):
    """記録を計算する"""
    adjust = 0
    if use_5to4:
        adjust += 1800
    if use_plus_coin:
        adjust += 500
    
    final_coin = boost_coin - adjust
    if final_coin < 0:
        final_coin = 0
    
    rate_raw = boost_coin / base_coin if base_coin > 0 else 0
    rate = snap_rate_to_multiplier(rate_raw)
    
    return {
        "base": int(base_coin),
        "boost": int(boost_coin),
        "final": int(final_coin),
        "rate_raw": round(rate_raw, 6),
        "rate": float(round(rate, 3))
    }

def show_secrets_info():
    """Secrets設定情報を表示"""
    st.info("""
    **💡 Streamlit Secrets設定について**
    
    このアプリはStreamlit Secretsからの設定読み込みに対応しています。
    
    **secrets.toml** ファイル（ローカル開発用）または Cloud Secrets（デプロイ時）で以下を設定できます：
    
    ```toml
    # GitHub設定
    GITHUB_TOKEN = "ghp_your_token_here"
    GITHUB_OWNER = "your-username"
    GITHUB_REPO = "your-repo-name"
    GITHUB_PATH = "coin_data_multi.json"
    
    # Discord設定
    DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/..."
    AUTO_SEND_DISCORD = true
    AUTO_SEND_JSON = false
    ```
    
    Secretsが設定されている場合は、それらの値が自動的に使用されます。
    設定されていない場合は、手動で入力できます。
    """)

def check_secrets_status():
    """Secrets設定の状況を確認・表示"""
    try:
        # GitHub関連のSecrets確認
        github_secrets = {
            'GITHUB_TOKEN': 'GITHUB_TOKEN' in st.secrets or 'github_token' in st.secrets,
            'GITHUB_OWNER': 'GITHUB_OWNER' in st.secrets or 'github_owner' in st.secrets,
            'GITHUB_REPO': 'GITHUB_REPO' in st.secrets or 'github_repo' in st.secrets,
            'GITHUB_PATH': 'GITHUB_PATH' in st.secrets or 'github_path' in st.secrets,
        }
        
        # Discord関連のSecrets確認
        discord_secrets = {
            'DISCORD_WEBHOOK_URL': 'DISCORD_WEBHOOK_URL' in st.secrets or 'discord_webhook_url' in st.secrets,
            'AUTO_SEND_DISCORD': 'AUTO_SEND_DISCORD' in st.secrets or 'auto_send_discord' in st.secrets,
            'AUTO_SEND_JSON': 'AUTO_SEND_JSON' in st.secrets or 'auto_send_json' in st.secrets,
        }
        
        github_count = sum(github_secrets.values())
        discord_count = sum(discord_secrets.values())
        
        if github_count > 0 or discord_count > 0:
            st.success(f"✅ Secrets設定検出: GitHub({github_count}/4項目), Discord({discord_count}/3項目)")
            return True
    except Exception:
        pass
    
    return False

def main():
    st.set_page_config(
        page_title="ツムツム コイン記録ツール",
        page_icon="🪙",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    
    st.title("🪙 ツムツム コイン記録ツール")
    st.subheader("Streamlit Secrets対応版 永続データ保存")
    
    # Secrets設定状況の確認
    secrets_configured = check_secrets_status()
    
    # サイドバーで設定
    with st.sidebar:
        # Secrets情報表示
        st.header("⚙️ 設定情報")
        
        with st.expander("💡 Secrets設定について", expanded=not secrets_configured):
            show_secrets_info()
        
        # GitHub設定
        st.header("🐙 GitHub設定")
        
        # Secretsから設定値を取得してデフォルト値として使用
        default_github_token = get_config_value('github_token', 'GITHUB_TOKEN')
        default_github_owner = get_config_value('github_owner', 'GITHUB_OWNER')
        default_github_repo = get_config_value('github_repo', 'GITHUB_REPO')
        default_github_path = get_config_value('github_path', 'GITHUB_PATH', DATA_FILE)
        
        # Secretsで設定されている項目は読み取り専用表示
        if default_github_token and ('GITHUB_TOKEN' in st.secrets or 'github_token' in st.secrets):
            st.text_input(
                "GitHub Personal Access Token",
                value="*** Secretsで設定済み ***",
                disabled=True,
                help="この値はStreamlit Secretsで設定されています"
            )
            github_token = default_github_token
        else:
            github_token = st.text_input(
                "GitHub Personal Access Token",
                value=st.session_state.get('github_token', ''),
                type="password",
                placeholder="ghp_...",
                help="GitHubのPersonal Access Tokenを入力してください。repo権限が必要です。"
            )
            st.session_state.github_token = github_token
        
        if default_github_owner and ('GITHUB_OWNER' in st.secrets or 'github_owner' in st.secrets):
            st.text_input(
                "GitHubユーザー名/組織名",
                value=default_github_owner,
                disabled=True,
                help="この値はStreamlit Secretsで設定されています"
            )
            github_owner = default_github_owner
        else:
            github_owner = st.text_input(
                "GitHubユーザー名/組織名",
                value=st.session_state.get('github_owner', ''),
                placeholder="User-Name",
                help="GitHubのユーザー名または組織名"
            )
            st.session_state.github_owner = github_owner
        
        if default_github_repo and ('GITHUB_REPO' in st.secrets or 'github_repo' in st.secrets):
            st.text_input(
                "リポジトリ名",
                value=default_github_repo,
                disabled=True,
                help="この値はStreamlit Secretsで設定されています"
            )
            github_repo = default_github_repo
        else:
            github_repo = st.text_input(
                "リポジトリ名",
                value=st.session_state.get('github_repo', ''),
                placeholder="tsumucoin",
                help="データを保存するリポジトリ名"
            )
            st.session_state.github_repo = github_repo
        
        if default_github_path and ('GITHUB_PATH' in st.secrets or 'github_path' in st.secrets):
            st.text_input(
                "ファイルパス",
                value=default_github_path,
                disabled=True,
                help="この値はStreamlit Secretsで設定されています"
            )
            github_path = default_github_path
        else:
            github_path = st.text_input(
                "ファイルパス",
                value=st.session_state.get('github_path', DATA_FILE),
                placeholder="coin_data_multi.json",
                help="GitHub上でのファイルパス"
            )
            st.session_state.github_path = github_path
        
        # GitHub接続テスト
        if github_token and github_owner and github_repo:
            if st.button("🧪 GitHub接続テスト"):
                data, error = get_github_file(github_token, github_owner, github_repo, github_path)
                if error:
                    st.error(f"❌ 接続失敗: {error}")
                else:
                    st.success(f"✅ 接続成功！ ({len(data)} ツムのデータ)")
        
        # 最後の保存状況
        if 'last_github_save' in st.session_state:
            status = st.session_state.last_github_save
            if "成功" in status:
                st.success(f"💾 GitHub保存: {status}")
            else:
                st.error(f"💾 GitHub保存: {status}")
        
        st.divider()
        
        # Discord Webhook設定
        st.header("🔗 Discord設定")
        
        # Secretsから設定値を取得
        default_webhook_url = get_config_value('discord_webhook_url', 'DISCORD_WEBHOOK_URL')
        default_auto_send_discord = get_config_value('auto_send_discord', 'AUTO_SEND_DISCORD', False)
        default_auto_send_json = get_config_value('auto_send_json', 'AUTO_SEND_JSON', False)
        
        # Webhook URL設定
        if default_webhook_url and ('DISCORD_WEBHOOK_URL' in st.secrets or 'discord_webhook_url' in st.secrets):
            st.text_input(
                "Discord Webhook URL",
                value="*** Secretsで設定済み ***",
                disabled=True,
                help="この値はStreamlit Secretsで設定されています"
            )
            webhook_url = default_webhook_url
        else:
            webhook_url = st.text_input(
                "Discord Webhook URL",
                value=st.session_state.get('discord_webhook_url', ''),
                type="password",
                placeholder="https://discord.com/api/webhooks/...",
                help="DiscordサーバーのWebhook URLを入力してください"
            )
            st.session_state.discord_webhook_url = webhook_url
        
        # 自動送信設定（Secretsの値を優先、ただし手動で変更可能）
        if isinstance(default_auto_send_discord, bool):
            initial_auto_send_discord = default_auto_send_discord
        else:
            initial_auto_send_discord = st.session_state.get('auto_send_discord', False)
        
        auto_send_discord = st.checkbox(
            "📤 記録追加時に自動でDiscordに送信",
            value=initial_auto_send_discord,
            help="記録を追加した際に自動的にDiscordに送信します"
        )
        st.session_state.auto_send_discord = auto_send_discord
        
        if isinstance(default_auto_send_json, bool):
            initial_auto_send_json = default_auto_send_json
        else:
            initial_auto_send_json = st.session_state.get('auto_send_json', False)
        
        auto_send_json = st.checkbox(
            "📄 データ変更時にJSONファイルも送信",
            value=initial_auto_send_json,
            help="記録を追加した際にJSONファイル全体もDiscordに送信します（バックアップ用）"
        )
        st.session_state.auto_send_json = auto_send_json
        
        # Discord テスト
        if webhook_url:
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🧪 記録テスト", help="Discord接続をテストします"):
                    test_record = {
                        "base": 1000,
                        "boost": 2000,
                        "final": 2000,
                        "rate_raw": 2.0,
                        "rate": 2.0
                    }
                    success, message = send_to_discord(webhook_url, "テストツム", test_record)
                    if success:
                        st.success(message)
                    else:
                        st.error(message)
            
            with col2:
                if st.button("📄 JSON送信テスト", help="JSONファイル送信をテストします"):
                    test_data = {
                        "テストツム": [
                            {
                                "base": 1000,
                                "boost": 2000,
                                "final": 2000,
                                "rate_raw": 2.0,
                                "rate": 2.0
                            }
                        ]
                    }
                    success, message = send_json_to_discord(webhook_url, test_data, "test_data.json")
                    if success:
                        st.success(message)
                    else:
                        st.error(message)
        
        st.divider()
        
        st.header("📁 データ管理")
        
        # 既存JSONファイルのアップロード
        uploaded_file = st.file_uploader(
            "既存のJSONファイルを読み込み",
            type="json",
            help="PCツールで作成されたcoin_data_multi.jsonファイルをアップロードできます"
        )
        
        if uploaded_file is not None:
            try:
                content = uploaded_file.read().decode('utf-8')
                data = json.loads(content)
                save_data_to_session(data)
                st.success("JSONファイルを読み込みました！")
            except Exception as e:
                st.error(f"ファイル読み込みエラー: {e}")
        
        st.divider()
        
        # データ操作ボタン
        st.header("🔄 データ操作")
        
        if st.button("🔄 GitHubから最新データを読み込み", help="GitHubから最新のデータを取得します"):
            if github_token and github_owner and github_repo:
                data, error = get_github_file(github_token, github_owner, github_repo, github_path)
                if error:
                    st.error(f"読み込みエラー: {error}")
                else:
                    st.session_state.coin_data = data
                    st.success(f"✅ GitHubからデータを読み込みました ({len(data)} ツム)")
                    st.rerun()
            else:
                st.error("GitHub設定が不完全です")
        
        data_for_save = load_existing_data()
        if data_for_save and st.button("💾 手動でGitHubに保存", help="現在のデータを手動でGitHubに保存します"):
            if github_token and github_owner and github_repo:
                success, message = save_to_github(github_token, github_owner, github_repo, github_path, data_for_save)
                if success:
                    st.success(message)
                    st.session_state.last_github_save = "成功"
                else:
                    st.error(message)
                    st.session_state.last_github_save = f"失敗: {message}"
            else:
                st.error("GitHub設定が不完全です")
        
        # 全データ削除機能
        st.divider()
        st.header("🗑️ データ削除")
        
        if data_for_save:
            total_records = sum(len(records) for records in data_for_save.values())
            st.warning(f"**注意**: 現在 {len(data_for_save)} ツム、{total_records} 件の記録があります")
            
            # 1段階確認
            if 'confirm_delete_all' not in st.session_state:
                st.session_state.confirm_delete_all = False
            
            if not st.session_state.confirm_delete_all:
                if st.button("🗑️ 全データを削除", help="すべてのツムと記録を完全に削除します", type="secondary"):
                    st.session_state.confirm_delete_all = True
                    st.rerun()
            else:
                st.error("⚠️ **警告**: この操作は取り消せません！")
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("❌ キャンセル", help="削除をキャンセルします"):
                        st.session_state.confirm_delete_all = False
                        st.rerun()
                with col2:
                    if st.button("💀 削除実行", help="すべてのデータを削除します", type="primary"):
                        # セッションデータ削除
                        empty_data = {}
                        save_data_to_session(empty_data)
                        st.success("✅ すべてのデータを削除しました")
                        
                        # 確認状態をリセット
                        st.session_state.confirm_delete_all = False
                        st.rerun()
        else:
            st.info("削除するデータがありません")
    
    # メインデータ
    data = load_existing_data()
    
    # ツム選択/新規作成
    st.header("🎯 ツム選択")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # 既存ツムのリスト
        existing_tsums = list(data.keys()) if data else []
        
        if existing_tsums:
            selected_option = st.radio(
                "ツムを選択してください",
                ["既存のツムを選択", "新しいツムを作成"],
                horizontal=True
            )
            
            if selected_option == "既存のツムを選択":
                selected_tsum = st.selectbox(
                    "既存のツム",
                    existing_tsums,
                    help="既存のツムから選択"
                )
            else:
                selected_tsum = st.text_input(
                    "新しいツム名",
                    placeholder="ツム名を入力してください",
                    help="新しいツム名を入力"
                )
        else:
            st.info("まだツムが登録されていません。新しいツムを作成してください。")
            selected_tsum = st.text_input(
                "新しいツム名",
                placeholder="ツム名を入力してください",
                help="新しいツム名を入力"
            )
    
    with col2:
        if selected_tsum and selected_tsum in data:
            records_count = len(data[selected_tsum])
            st.metric("記録数", records_count)
            
            if records_count > 0:
                avg_rate = sum(r["rate"] for r in data[selected_tsum]) / records_count
                st.metric("平均倍率", f"{avg_rate:.3f}")
    
    # 入力フォーム
    if selected_tsum:
        st.header("📝 データ入力")
        
        # アイテム選択
        col1, col2 = st.columns(2)
        with col1:
            use_5to4 = st.checkbox("5→4 (1800コイン)", help="5→4アイテムを使用した場合")
        with col2:
            use_plus_coin = st.checkbox("+Coin (500コイン)", help="+Coinアイテムを使用した場合")
        
        # コイン入力
        col1, col2 = st.columns(2)
        with col1:
            base_coin = st.number_input(
                "ベースコイン",
                min_value=1,
                max_value=100000,
                value=1000,
                step=100,
                help="アイテム使用前の基本コイン数"
            )
        
        with col2:
            boost_coin = st.number_input(
                "最終コイン",
                min_value=1,
                max_value=500000,
                value=2000,
                step=100,
                help="実際に獲得したコイン数"
            )
        
        # プレビュー計算
        if base_coin > 0 and boost_coin > 0:
            preview_record = calculate_record(base_coin, boost_coin, use_5to4, use_plus_coin)
            
            st.subheader("📊 計算結果プレビュー")
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric("ベースコイン", f"{preview_record['base']:,}")
            with col2:
                st.metric("Boostコイン", f"{preview_record['boost']:,}")
            with col3:
                st.metric("Finalコイン", f"{preview_record['final']:,}")
            with col4:
                st.metric("倍率", f"{preview_record['rate']:.3f}")
            
            # アイテムコスト表示
            if use_5to4 or use_plus_coin:
                item_cost = 0
                if use_5to4:
                    item_cost += 1800
                if use_plus_coin:
                    item_cost += 500
                st.info(f"アイテムコスト: {item_cost:,}コイン")
        
        # Discord設定を取得（Secrets優先）
        webhook_url = get_config_value('discord_webhook_url', 'DISCORD_WEBHOOK_URL')
        auto_send_discord = get_config_value('auto_send_discord', 'AUTO_SEND_DISCORD', False)
        auto_send_json = get_config_value('auto_send_json', 'AUTO_SEND_JSON', False)
        
        # セッション状態も確認（手動設定を優先）
        if 'auto_send_discord' in st.session_state:
            auto_send_discord = st.session_state['auto_send_discord']
        if 'auto_send_json' in st.session_state:
            auto_send_json = st.session_state['auto_send_json']
        
        # 記録追加ボタン（Discord機能の有無で分岐）
        if webhook_url:
            # Discord機能が有効な場合：3つのボタン
            col1, col2, col3 = st.columns([2, 1, 1])
            
            with col1:
                add_record_btn = st.button("📝 記録を追加", type="primary", use_container_width=True)
            
            with col2:
                manual_discord_send = st.button("📤 記録送信", use_container_width=True, help="現在の記録をDiscordに送信")
            
            with col3:
                manual_json_send = st.button("📄 JSON送信", use_container_width=True, help="全データをJSONファイルとしてDiscordに送信")
        else:
            # Discord機能が無効な場合：記録追加のみ
            add_record_btn = st.button("📝 記録を追加", type="primary", use_container_width=True)
            manual_discord_send = False
            manual_json_send = False
        
        # 記録追加処理
        if add_record_btn:
            if base_coin > 0 and boost_coin > 0:
                record = calculate_record(base_coin, boost_coin, use_5to4, use_plus_coin)
                
                # データに追加
                if selected_tsum not in data:
                    data[selected_tsum] = []
                
                data[selected_tsum].append(record)
                save_data_to_session(data)
                
                st.success(f"✅ {selected_tsum} の記録を追加しました！")
                
                # 自動Discord送信
                if auto_send_discord and webhook_url:
                    success, message = send_to_discord(webhook_url, selected_tsum, record, use_5to4, use_plus_coin)
                    if success:
                        st.success("📤 " + message)
                    else:
                        st.error("📤 " + message)
                
                # 自動JSON送信
                if auto_send_json and webhook_url:
                    success, message = send_json_to_discord(webhook_url, data)
                    if success:
                        st.success("📄 " + message)
                    else:
                        st.error("📄 " + message)
                
                # 入力フォームをリセット（オプション）
                st.rerun()
            else:
                st.error("❌ 正しいコイン数を入力してください")
        
        # 手動Discord送信処理
        if manual_discord_send:
            if base_coin > 0 and boost_coin > 0:
                record = calculate_record(base_coin, boost_coin, use_5to4, use_plus_coin)
                success, message = send_to_discord(webhook_url, selected_tsum, record, use_5to4, use_plus_coin)
                if success:
                    st.success("📤 " + message)
                else:
                    st.error("📤 " + message)
            else:
                st.error("❌ 正しいコイン数を入力してください")
        
        # 手動JSON送信処理
        if manual_json_send:
            if data:
                success, message = send_json_to_discord(webhook_url, data)
                if success:
                    st.success("📄 " + message)
                else:
                    st.error("📄 " + message)
            else:
                st.error("❌ 送信するデータがありません")
    
    # データ表示
    if data and selected_tsum and selected_tsum in data:
        st.header(f"📋 {selected_tsum} の記録履歴")
        
        records = data[selected_tsum]
        if records:
            # 最新の記録から表示
            records_reversed = list(reversed(records))
            
            # テーブル形式で表示
            df_records = []
            for i, record in enumerate(records_reversed):
                df_records.append({
                    "No.": len(records) - i,
                    "ベースコイン": f"{record['base']:,}",
                    "Boostコイン": f"{record['boost']:,}",
                    "Finalコイン": f"{record['final']:,}",
                    "倍率": f"{record['rate']:.3f}",
                })
            
            df = pd.DataFrame(df_records)
            st.dataframe(df, use_container_width=True)
            
            # 統計情報
            st.subheader("📊 統計情報")
            col1, col2, col3, col4 = st.columns(4)
            
            avg_rate = sum(r["rate"] for r in records) / len(records)
            max_rate = max(r["rate"] for r in records)
            min_rate = min(r["rate"] for r in records)
            total_final = sum(r["final"] for r in records)
            
            with col1:
                st.metric("平均倍率", f"{avg_rate:.3f}")
            with col2:
                st.metric("最高倍率", f"{max_rate:.3f}")
            with col3:
                st.metric("最低倍率", f"{min_rate:.3f}")
            with col4:
                st.metric("総獲得コイン", f"{total_final:,}")
            
            # 記録削除機能とJSON送信ボタン
            st.divider()
            col1, col2 = st.columns(2)
            with col1:
                if st.button("🗑️ 最新の記録を削除", help="最後に追加した記録を削除します"):
                    if st.session_state.get('confirm_delete', False):
                        data[selected_tsum].pop()
                        if not data[selected_tsum]:  # 記録が空になった場合
                            del data[selected_tsum]
                        save_data_to_session(data)
                        st.session_state.confirm_delete = False
                        st.success("記録を削除しました")
                        st.rerun()
                    else:
                        st.session_state.confirm_delete = True
                        st.warning("もう一度クリックして削除を確定してください")
            
            with col2:
                # JSONファイル送信ボタン（記録がある場合のみ表示）
                webhook_url_for_json = get_config_value('discord_webhook_url', 'DISCORD_WEBHOOK_URL')
                if webhook_url_for_json and st.button("📄 全記録をDiscordに送信", help="現在のすべてのデータをJSONファイルとしてDiscordに送信"):
                    success, message = send_json_to_discord(webhook_url_for_json, data)
                    if success:
                        st.success("📄 " + message)
                    else:
                        st.error("📄 " + message)
    
    # データダウンロード機能
    st.header("💾 データダウンロード")
    
    if data:
        # JSON文字列を生成
        json_str = json.dumps(data, ensure_ascii=False, indent=2)
        
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.text_area(
                "JSON データプレビュー",
                json_str,
                height=200,
                help="PCツールで読み込み可能なJSON形式"
            )
        
        with col2:
            st.download_button(
                label="📥 JSONファイルをダウンロード",
                data=json_str,
                file_name="coin_data_multi.json",
                mime="application/json",
                help="PCツール用のJSONファイルとしてダウンロード",
                use_container_width=True
            )
            
            # 統計情報
            total_tsums = len(data)
            total_records = sum(len(records) for records in data.values())
            st.metric("ツム数", total_tsums)
            st.metric("総記録数", total_records)
    else:
        st.info("まだデータがありません。ツムを選択して記録を追加してください。")
    
    # セットアップガイド
    st.header("🛠️ セットアップガイド")
    
    with st.expander("⚙️ Streamlit Secrets設定方法", expanded=False):
        st.markdown("""
        ### Streamlit Secretsとは
        
        Streamlit Secretsは、パスワードやAPIキーなどの機密情報を安全に管理する機能です。
        
        ### ローカル開発での設定
        
        プロジェクトのルートディレクトリに `.streamlit/secrets.toml` ファイルを作成：
        
        ```toml
        # .streamlit/secrets.toml
        
        # GitHub設定
        GITHUB_TOKEN = "ghp_your_personal_access_token_here"
        GITHUB_OWNER = "your-github-username"
        GITHUB_REPO = "your-repository-name"
        GITHUB_PATH = "coin_data_multi.json"
        
        # Discord設定
        DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/..."
        AUTO_SEND_DISCORD = true
        AUTO_SEND_JSON = false
        ```
        
        ### Streamlit Cloudでの設定
        
        1. Streamlit Cloud のアプリダッシュボードにアクセス
        2. **Settings** → **Secrets** セクションを開く
        3. 上記と同じ形式でsecretsを設定
        4. **Save** をクリック
        
        ### 設定項目の説明
        
        **GitHub設定:**
        - `GITHUB_TOKEN`: Personal Access Token (repo権限必要)
        - `GITHUB_OWNER`: GitHubユーザー名または組織名
        - `GITHUB_REPO`: データ保存用リポジトリ名
        - `GITHUB_PATH`: 保存するファイル名 (通常: coin_data_multi.json)
        
        **Discord設定:**
        - `DISCORD_WEBHOOK_URL`: Discord Webhook URL
        - `AUTO_SEND_DISCORD`: 記録追加時の自動送信 (true/false)
        - `AUTO_SEND_JSON`: JSON自動送信 (true/false)
        
        ### セキュリティ上の注意
        
        - `secrets.toml` ファイルは `.gitignore` に追加してください
        - Personal Access Token は他人に見せないでください
        - 定期的にトークンを再生成することを推奨します
        """)
    
    with st.expander("📖 GitHub連携の設定方法", expanded=False):
        st.markdown("""
        ### 1. GitHub Personal Access Tokenの作成
        
        1. [GitHub Settings > Developer settings > Personal access tokens](https://github.com/settings/tokens) にアクセス
        2. **Generate new token (classic)** をクリック
        3. **Note** に「ツムツムデータ保存用」などと入力
        4. **Expiration** で有効期限を設定（推奨：90日以上）
        5. **Scopes** で **repo** にチェック（全てのレポジトリアクセス権限）
        6. **Generate token** をクリック
        7. 表示されたトークン（`ghp_`で始まる文字列）をコピーして保存
        
        ### 2. データ保存用リポジトリの準備
        
        **Option A: 新しいリポジトリを作成**
        1. GitHubで新しいリポジトリを作成（例：`tsum-coin-data`）
        2. **Private** または **Public** を選択
        3. **Initialize with README** はチェックしなくてもOK
        
        **Option B: 既存のリポジトリを使用**
        - 既存のリポジトリにデータファイルを保存することも可能
        
        ### 3. Secrets設定（推奨）
        
        機密情報はStreamlit Secretsで管理することを強く推奨します。
        上記の「Streamlit Secrets設定方法」を参照してください。
        
        ### 4. 手動設定（Secretsを使わない場合）
        
        サイドバーの「GitHub設定」セクションで直接入力も可能ですが、
        セキュリティ上の理由でSecretsの使用を推奨します。
        
        ### 5. 動作確認
        
        - **🧪 GitHub接続テスト** ボタンで接続確認
        - 記録を追加すると自動的にGitHubに保存されます
        - **🔄 GitHubから最新データを読み込み** で他のデバイスからも同じデータにアクセス可能
        """)
    
    with st.expander("💡 使用方法のヒント", expanded=False):
        st.markdown("""
        ### Secrets活用のメリット
        
        - **セキュリティ**: 機密情報がコードに含まれない
        - **利便性**: 毎回入力する必要がない
        - **共有**: 複数の環境で同じ設定を使用可能
        - **管理**: 一箇所で設定を管理
        
        ### データの永続化について
        
        - **GitHub連携**: 設定すると全てのデータがGitHubに自動保存され、再起動後もデータが保持されます
        - **ローカル保存**: GitHub設定がない場合、ローカルファイルに保存されますが、Streamlit Cloud では再起動時に消える可能性があります
        
        ### 複数デバイスでの利用
        
        1. 各デバイス/環境で同じSecrets設定を行う
        2. **🔄 GitHubから最新データを読み込み** で最新状態に同期
        3. データ追加は自動的にGitHubに反映される
        
        ### バックアップとリストア
        
        - **📥 JSONファイルをダウンロード**: ローカルバックアップを作成
        - **既存のJSONファイルを読み込み**: バックアップファイルから復元
        - Discord連携でJSON自動送信も可能
        
        ### トラブルシューティング
        
        - GitHub保存に失敗した場合、ローカルファイルにも保存されます
        - 接続エラーが続く場合は、トークンの権限とリポジトリ名を確認してください
        - データが見つからない場合は、**🔄 GitHubから最新データを読み込み** を試してください
        - Secrets設定が反映されない場合は、アプリを再起動してください
        """)
    
    # フッター
    st.markdown("---")
    st.markdown(
        "**ツムツム コイン記録ツール - Streamlit Secrets対応版**  \n"
        "Streamlit Secretsによる安全な設定管理と、GitHub連携による永続データ保存を実現。  \n"
        "PCツール互換のJSONファイル形式でデータを管理し、Discord連携も可能です。"
    )

if __name__ == "__main__":
    main()