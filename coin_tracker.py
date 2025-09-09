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
    st.header("🎯 ツム選