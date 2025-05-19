import streamlit as st
import yaml
import os
from pathlib import Path
import autogen
from dotenv import load_dotenv # .envファイル読み込みのため追加
from typing import Dict, List, Tuple # Tupleを追加
import re # 正規表現モジュールをインポート
from datetime import datetime # datetimeをインポート

from core.file_utils import get_project_structure_text, get_java_files, sanitize_filename, save_markdown_to_file # sanitize_filename と save_markdown_to_file を追加
from agents.codebase_analyzer_agent import CodebaseAnalyzerAgent
from agents.api_design_generator_agent import APIDesignGeneratorAgent
from agents.db_design_generator_agent import DBDesignGeneratorAgent
from agents.user_proxy_agent import StreamlitUserProxyAgent
# from agents.assistant_agent import get_llm_config_from_app # Agent内で呼び出すので不要かも

# .envファイルから環境変数を読み込む (アプリケーションの最初の方で呼び出す)
load_dotenv()

# 設定ファイルのパス
CONFIG_FILE_PATH = Path(__file__).resolve().parent / "configs" / "app_config.yaml"

# グローバル変数として設定を保持 (アプリケーション全体で利用するため)
APP_CONFIG = {}

# --- 設定読み込み関数 ---
def load_config():
    """
    configs/app_config.yaml から設定を読み込み、グローバル変数 APP_CONFIG に格納します。
    """
    global APP_CONFIG
    try:
        with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
            APP_CONFIG = yaml.safe_load(f)
        if not APP_CONFIG: # 空のファイルや不正な形式の場合
            st.error("設定ファイル (app_config.yaml) の読み込みに失敗しました。内容を確認してください。")
            APP_CONFIG = {} # エラー時もAPP_CONFIGが定義されるようにする
            return False
        
        # OpenAI APIキーの確認 (dotenvで読み込まれたか)
        if not os.getenv("OPENAI_API_KEY"):
            st.error(
                "環境変数 OPENAI_API_KEY が設定されていません。.envファイルを作成し、キーを記述してください。"
            )
            # return False # キーがなくても起動はさせるが、Agent呼び出しで失敗する

        # LLM設定の検証
        llm_conf = APP_CONFIG.get('llm_config', {})
        if not llm_conf.get('model'):
             st.warning(
                "app_config.yaml の llm_config に `model` が指定されていません。 "
                "動作しない可能性があります。"
            )
        return True
    except FileNotFoundError:
        st.error(f"設定ファイルが見つかりません: {CONFIG_FILE_PATH}")
        APP_CONFIG = {}
        return False
    except yaml.YAMLError as e:
        st.error(f"設定ファイルの解析中にエラーが発生しました: {e}")
        APP_CONFIG = {}
        return False
    except Exception as e:
        st.error(f"設定ファイルの読み込み中に予期せぬエラーが発生しました: {e}")
        APP_CONFIG = {}
        return False

# display_directory_tree 関数は core.file_utils.get_project_structure_text に置き換えられたため削除

def parse_api_endpoints_from_report(analysis_report_text: str) -> List[Tuple[str, str]]:
    """
    CodebaseAnalyzerAgentの分析レポートからAPIエンドポイントのリストを抽出します。
    各APIのタイトル (例: "API 1: GET /api/users/{id}") と詳細情報をタプルで返します。
    """
    api_endpoints = []
    try:
        api_list_match = re.search(r"API_LIST_START(.*?)API_LIST_END", analysis_report_text, re.DOTALL)
        if api_list_match:
            api_content = api_list_match.group(1).strip()
            # "### API X:" または "### API X (追加情報):" のようなパターンで分割
            # 各APIブロックは "### API" で始まる想定
            raw_apis = re.split(r"(?=### API\s*\d*[:\s])", api_content)
            for api_block in raw_apis:
                api_block = api_block.strip()
                if not api_block.startswith("### API"):
                    continue

                title_match = re.search(r"###\s*(API\s*\d*[:\s]*.*?)\n", api_block, re.IGNORECASE)
                api_title = title_match.group(1).strip() if title_match else f"API Endpoint {len(api_endpoints) + 1}"

                http_method_match = re.search(r"-\s*HTTPメソッド\s*:\s*(.+)", api_block, re.IGNORECASE)
                path_match = re.search(r"-\s*パス\s*:\s*(.+)", api_block, re.IGNORECASE)
                
                identifier = api_title # デフォルト
                if http_method_match and path_match:
                    identifier = f"{http_method_match.group(1).strip()} {path_match.group(1).strip()}"
                
                api_endpoints.append((identifier, api_block))
        
        if not api_endpoints and "API_LIST_START" in analysis_report_text:
             st.warning("API_LIST_START/ENDブロックは検出されましたが、個別のAPI情報を抽出できませんでした。CodebaseAnalyzerAgentの出力形式を確認してください。")
        elif not api_endpoints:
            st.info("分析レポート内にAPI_LIST_START/ENDブロックが見つかりませんでした。APIは検出されなかった可能性があります。")

    except Exception as e:
        st.error(f"APIエンドポイントの解析中にエラーが発生しました: {e}")
    return api_endpoints

def run_full_analysis_pipeline(codebase_path_str: str, java_files_list: List[Path], dir_tree_str: str, status_container=None) -> Dict[str, any]:
    """
    コード分析から設計書生成までの完全なパイプラインを実行します。
    結果は st.session_state に直接書き込まれます。
    """
    global APP_CONFIG
    results = {"status": "Error", "message": "パイプラインの開始に失敗しました。", 
                 "initial_analysis": "", "api_docs": {}, "db_doc": ""}

    def log_to_status(message, level="info"):
        if status_container:
            if level == "error":
                status_container.write(f"⚠️ {message}")
            elif level == "warning":
                status_container.write(f"👀 {message}")
            else:
                status_container.write(f"➡️ {message}")
        else: 
            if level == "error": st.error(message)
            elif level == "warning": st.warning(message)
            else: st.info(message)

    if not APP_CONFIG:
        results["message"] = "アプリケーション設定がロードされていません。処理を中止します。"
        log_to_status(results["message"], "error")
        return results
    
    if not os.getenv("OPENAI_API_KEY"):
        results["message"] = "OPENAI_API_KEYが設定されていません。.envファイルを確認してください。Agent処理をスキップします。"
        log_to_status(results["message"], "error")
        return results

    try:
        user_proxy = StreamlitUserProxyAgent(
            name="StreamlitUserProxy",
            human_input_mode="NEVER",
            code_execution_config=False,
        )

        st.session_state.analysis_results_text = ""
        st.session_state.api_documents = {}
        st.session_state.db_document = ""
        st.session_state.project_overview_text = f"### {APP_CONFIG.get('ui_texts', {}).get('directory_structure_title', 'ディレクトリ構造')}\n```\n{dir_tree_str}\n```\n\n"
        st.session_state.project_overview_text += f"### {APP_CONFIG.get('ui_texts', {}).get('java_files_title', '検出されたJavaファイル')}\n"
        st.session_state.project_overview_text += "\n".join([f"- {f.name} ({f.relative_to(Path(codebase_path_str))})" for f in java_files_list[:20]])
        if len(java_files_list) > 20:
            st.session_state.project_overview_text += f"\n...他{len(java_files_list) - 20}ファイル"

        log_to_status("ステップ3.1: CodebaseAnalyzerAgent との対話を開始します (コード分析中)...")
        analyzer = CodebaseAnalyzerAgent(app_config=APP_CONFIG)
        initial_analysis_prompt = analyzer.analyze_codebase(
            codebase_path=codebase_path_str,
            java_files=java_files_list,
            project_structure=dir_tree_str
        )
        
        user_proxy.initiate_chat(recipient=analyzer, message=initial_analysis_prompt, max_turns=1, clear_history=True)
        analysis_report_message = user_proxy.last_message(agent=analyzer)

        if not (analysis_report_message and analysis_report_message.get("content")):
            results["message"] = "CodebaseAnalyzerAgentから有効な分析レポートを取得できませんでした。"
            log_to_status(results["message"], "warning")
            st.session_state.analysis_results_text = results["message"]
            return results
        
        analysis_report_text = str(analysis_report_message["content"])
        st.session_state.analysis_results_text = analysis_report_text
        results["initial_analysis"] = analysis_report_text
        log_to_status("CodebaseAnalyzerAgentによる初期分析が完了しました。")

        api_endpoints = parse_api_endpoints_from_report(analysis_report_text)
        
        if not api_endpoints:
            log_to_status("CodebaseAnalyzerAgentの分析結果からAPIエンドポイントが見つかりませんでした。API設計書の生成はスキップされます。")
        else:
            log_to_status(f"ステップ3.2: {len(api_endpoints)}件のAPIエンドポイントを検出。APIDesignGeneratorAgent との対話を開始します...")
            api_designer = APIDesignGeneratorAgent(app_config=APP_CONFIG)
            
            for i, (api_identifier, api_info_block) in enumerate(api_endpoints):
                log_to_status(f"  API設計書を生成中 ({i+1}/{len(api_endpoints)}): {api_identifier} ...")
                api_doc_prompt = api_designer.generate_api_document_prompt(
                    single_api_analysis=api_info_block,
                    full_analysis_report=analysis_report_text
                )
                
                user_proxy.initiate_chat(recipient=api_designer, message=api_doc_prompt, max_turns=1, clear_history=True)
                api_document_message = user_proxy.last_message(agent=api_designer)

                if api_document_message and api_document_message.get("content"):
                    doc_content = str(api_document_message["content"])
                    st.session_state.api_documents[api_identifier] = doc_content
                    results["api_docs"][api_identifier] = doc_content
                    log_to_status(f"  API「{api_identifier}」の設計書生成完了。")
                else:
                    error_msg = f"API「{api_identifier}」の設計書生成に失敗しました。"
                    log_to_status(error_msg, "warning")
                    st.session_state.api_documents[api_identifier] = error_msg
            
            if st.session_state.api_documents:
                 log_to_status(f"全{len(st.session_state.api_documents)}件のAPI設計書生成処理が完了しました。")

        log_to_status("ステップ3.3: DBDesignGeneratorAgent との対話を開始します (DB設計書生成中)...")
        db_designer = DBDesignGeneratorAgent(app_config=APP_CONFIG)
        db_doc_prompt = db_designer.generate_db_document_prompt(analysis_report_text)

        user_proxy.initiate_chat(recipient=db_designer, message=db_doc_prompt, max_turns=1, clear_history=True)
        db_document_message = user_proxy.last_message(agent=db_designer)

        if db_document_message and db_document_message.get("content"):
            st.session_state.db_document = str(db_document_message["content"])
            results["db_doc"] = st.session_state.db_document
            log_to_status("DBDesignGeneratorAgentによるDB設計書の生成が完了しました。")
        else:
            error_msg = "DBDesignGeneratorAgentから有効なDB設計書を取得できませんでした。"
            log_to_status(error_msg, "warning")
            st.session_state.db_document = error_msg
            results["db_doc"] = error_msg
        
        results["status"] = "Success"
        results["message"] = "設計書生成パイプラインが完了しました。"
        return results

    except Exception as e:
        results["message"] = f"Agent対話パイプラインエラー: {str(e)}"
        log_to_status(f"Agentの対話パイプライン中にエラーが発生しました: {e}", "error")
        return results

def main():
    global APP_CONFIG
    if not load_config():
        st.stop()

    ui_texts = APP_CONFIG.get('ui_texts', {})
    app_title = ui_texts.get('app_title', "コード分析・設計書生成システム")
    codebase_path_label = ui_texts.get('codebase_path_label', "分析対象のJavaコードベースへの絶対パス:")
    start_analysis_button_text = ui_texts.get('start_analysis_button', "分析開始")
    error_path_invalid = ui_texts.get('error_path_invalid', "有効なディレクトリパスを入力してください。")
    error_path_not_found = ui_texts.get('error_path_not_found', "指定されたパスが見つかりません。")
    analysis_in_progress_text = ui_texts.get('analysis_in_progress', "分析を実行中です。しばらくお待ちください...")
    results_title_text = ui_texts.get('results_title', "生成された設計ドキュメント")
    initial_analysis_title = ui_texts.get('initial_analysis_title', "初期分析結果 (Agent応答)")
    api_docs_tab_text = ui_texts.get('api_docs_tab', "API仕様書")
    db_docs_tab_text = ui_texts.get('db_docs_tab', "データベース設計書")
    mermaid_render_error_text = ui_texts.get('mermaid_render_error', "Mermaid図のレンダリングに失敗しました。コードを確認してください。")
    project_overview_tab_text = ui_texts.get('project_overview_tab', "プロジェクト概要")
    no_apis_found_text = ui_texts.get('no_apis_found', "APIエンドポイントは見つかりませんでした。")
    input_section_header_text = ui_texts.get('input_section_header', "1. 分析対象の指定")
    # save_documents_button_text = ui_texts.get('save_documents_button', "設計書を保存") # 旧ボタンのためコメントアウトまたは削除
    output_dir_name = APP_CONFIG.get('output_settings', {}).get('output_directory_name', "autogen_docs")
    project_overview_dir_name = APP_CONFIG.get('output_settings', {}).get('project_overview_subdir', "project_overview")
    api_specs_dir_name = APP_CONFIG.get('output_settings', {}).get('api_spec_subdir', "api_specifications")
    db_design_dir_name = APP_CONFIG.get('output_settings', {}).get('db_design_subdir', "database_design")
    # save_success_message_text = ui_texts.get('save_success_message', "設計書が {path} に保存されました。") # 旧ボタンのためコメントアウトまたは削除
    # save_error_message_text = ui_texts.get('save_error_message', "設計書の保存中にエラーが発生しました。") # 旧ボタンのためコメントアウトまたは削除
    no_documents_to_save_text = ui_texts.get('no_documents_to_save', "保存できる生成済みドキュメントがありません。")

    # 新しい一括保存ボタン用のUIテキスト
    save_all_to_project_root_button_text = ui_texts.get('save_all_to_project_root_button', "一括保存")
    save_all_success_message_text = ui_texts.get('save_all_success_message', "全ての設計書がプロジェクトルートの {path} に保存されました。")
    save_all_error_message_text = ui_texts.get('save_all_error_message', "設計書の一括保存(プロジェクトルート)中にエラーが発生しました。")

    st.set_page_config(page_title=app_title, layout="wide")
    st.title(f"🛠️ {app_title}")

    st.header(input_section_header_text)
    
    codebase_path_str = st.text_input(
        codebase_path_label,
        value=st.session_state.get("codebase_path", ""),
        placeholder="例: /Users/username/my-java-project",
        key="codebase_path_input_main"
    )
    st.session_state.codebase_path = codebase_path_str

    # ボタン用の列を定義
    col_start_analysis, col_save_all_docs = st.columns(2)

    with col_start_analysis:
        start_button_clicked = st.button(
            f"🚀 {start_analysis_button_text}", 
            key="start_analysis_button_main", 
            use_container_width=True
        )

    with col_save_all_docs:
        disable_save_all_button = not (st.session_state.get("documents_generated", False) and codebase_path_str)
        if st.button(
            f"📦 {save_all_to_project_root_button_text}", 
            key="save_all_to_project_root_button", 
            use_container_width=True,
            disabled=disable_save_all_button
        ):
            project_root_path = Path("/Users/user/code-agent") # ワークスペースのルートパス
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            unique_save_dir_name = f"generated_design_documents_{timestamp}"
            output_base_path_root = project_root_path / unique_save_dir_name

            save_errors_root = []
            saved_any_root = False

            try:
                # プロジェクト概要の保存
                if "project_overview_text" in st.session_state and st.session_state.project_overview_text:
                    overview_dir_root = output_base_path_root / project_overview_dir_name
                    success, error_msg = save_markdown_to_file(st.session_state.project_overview_text, overview_dir_root, "project_overview.md")
                    if success:
                        saved_any_root = True
                    else:
                        save_errors_root.append(f"项目概览保存失败: {error_msg}")
                
                # API仕様書の保存
                if "api_documents" in st.session_state and isinstance(st.session_state.api_documents, dict):
                    api_docs_dir_root = output_base_path_root / api_specs_dir_name
                    for api_name, doc_content in st.session_state.api_documents.items():
                        if isinstance(doc_content, str) and not doc_content.startswith("⚠️"):
                            safe_filename = sanitize_filename(api_name) + ".md"
                            success, error_msg = save_markdown_to_file(doc_content, api_docs_dir_root, safe_filename)
                            if success:
                                saved_any_root = True
                            else:
                                save_errors_root.append(f"API规范 '{api_name}' 保存失败: {error_msg}")
                
                # データベース設計書の保存
                if "db_document" in st.session_state and st.session_state.db_document:
                    if isinstance(st.session_state.db_document, str) and not st.session_state.db_document.startswith("⚠️"):
                        db_design_dir_root = output_base_path_root / db_design_dir_name
                        success, error_msg = save_markdown_to_file(st.session_state.db_document, db_design_dir_root, "database_design.md")
                        if success:
                            saved_any_root = True
                        else:
                            save_errors_root.append(f"数据库设计文档保存失败: {error_msg}")

                if not saved_any_root and not save_errors_root:
                    st.info(no_documents_to_save_text)
                elif save_errors_root:
                    for error in save_errors_root:
                        st.error(error)
                    st.error(save_all_error_message_text)
                else:
                    st.success(save_all_success_message_text.format(path=str(output_base_path_root.resolve())))
            
            except Exception as e:
                st.error(f"{save_all_error_message_text} 詳細: {str(e)}")

    if start_button_clicked:
        if not codebase_path_str:
            st.error(error_path_invalid)
        else:
            codebase_path = Path(codebase_path_str)
            if not codebase_path.is_dir():
                st.error(error_path_not_found)
            else:
                with st.status(analysis_in_progress_text, expanded=True) as status_container:
                    try:
                        status_container.write("ステップ1/4: プロジェクト構造を読み込み中...")
                        dir_tree = get_project_structure_text(codebase_path_str, max_depth=5, include_files=False)
                        status_container.write("ステップ2/4: Javaファイルを検索中...")
                        java_files = get_java_files(codebase_path_str)
                        
                        if not java_files:
                            st.warning("指定されたディレクトリにJavaファイルが見つかりませんでした。分析を中止します。")
                            status_container.update(label="Javaファイルが見つかりません", state="warning", expanded=False)
                            st.session_state.documents_generated = False # ドキュメント未生成状態に
                        else:
                            status_container.write("ステップ3/4: Agentによる分析と設計書生成を開始します...")
                            st.session_state.documents_generated = False # 分析開始時にリセット
                            pipeline_results = run_full_analysis_pipeline(codebase_path_str, java_files, dir_tree, status_container)
                            
                            if pipeline_results.get("status") == "Success":
                                status_container.update(label=pipeline_results.get("message", "分析完了！"), state="complete", expanded=False)
                                st.session_state.documents_generated = True 
                            else:
                                status_container.update(label=pipeline_results.get("message", "分析中にエラーが発生しました。\n詳細は上記ログを確認してください。"), state="error", expanded=True)
                                st.session_state.documents_generated = False
                    except Exception as e:
                        st.error(f"分析処理の準備中にエラーが発生しました: {e}")
                        st.exception(e)
                        status_container.update(label=f"分析準備エラー: {e}", state="error", expanded=True)
                        st.session_state.documents_generated = False
    
    st.markdown("---")
    st.header(results_title_text)

    tab_titles = [
        project_overview_tab_text,
        initial_analysis_title,
        api_docs_tab_text,
        db_docs_tab_text
    ]
    tab1, tab2, tab3, tab4 = st.tabs(tab_titles)

    with tab1:
        if "project_overview_text" in st.session_state and st.session_state.project_overview_text:
            st.markdown(st.session_state.project_overview_text)
        else:
            st.info(ui_texts.get('info_project_overview_empty', "分析を開始すると、ここにプロジェクトの概要情報が表示されます。"))

    with tab2:
        if "analysis_results_text" in st.session_state and st.session_state.analysis_results_text:
            with st.expander(ui_texts.get('expander_raw_analyzer_output', "CodebaseAnalyzerAgentの生出力を見る"), expanded=False):
                st.markdown(st.session_state.analysis_results_text)
        else:
            st.info(ui_texts.get('info_initial_analysis_empty', "分析を開始すると、ここにコード分析Agentの初期レポートが表示されます。"))
    
    with tab3:
        if "api_documents" in st.session_state and st.session_state.api_documents:
            if isinstance(st.session_state.api_documents, dict) and st.session_state.api_documents:
                api_tabs = st.tabs(list(st.session_state.api_documents.keys()))
                for i, api_name in enumerate(st.session_state.api_documents.keys()):
                    with api_tabs[i]:
                        st.subheader(api_name)
                        doc_content = st.session_state.api_documents[api_name]
                        parts = re.split(r"(```mermaid\n.*?\n```)", doc_content, flags=re.DOTALL)
                        for part_idx, part in enumerate(parts):
                            if part.startswith("```mermaid"):
                                mermaid_code = part.strip().replace("```mermaid", "").replace("```", "").strip()
                                try:
                                    st.markdown(f"```mermaid\n{mermaid_code}\n```")
                                except Exception as e_mermaid:
                                    st.warning(f"{mermaid_render_error_text} (詳細: {e_mermaid})")
                                    st.code(mermaid_code, language="mermaid")
                            else:
                                st.markdown(part, unsafe_allow_html=True)
            elif isinstance(st.session_state.api_documents, str):
                 st.warning(st.session_state.api_documents)
            else:
                st.info(no_apis_found_text)
        else:
            st.info(ui_texts.get('info_api_docs_empty', "分析が完了すると、ここにAPI仕様書が表示されます。"))

    with tab4:
        if "db_document" in st.session_state and st.session_state.db_document:
            parts = re.split(r"(```mermaid\n.*?\n```)", st.session_state.db_document, flags=re.DOTALL)
            for part in parts:
                if part.startswith("```mermaid"):
                    mermaid_code = part.strip().replace("```mermaid", "").replace("```", "").strip()
                    try:
                        st.markdown(f"```mermaid\n{mermaid_code}\n```")
                    except Exception as e_mermaid:
                        st.warning(f"{mermaid_render_error_text} (詳細: {e_mermaid})")
                        st.code(mermaid_code, language="mermaid")
                else:
                    st.markdown(part, unsafe_allow_html=True)
        else:
            st.info(ui_texts.get('info_db_docs_empty', "分析が完了すると、ここにデータベース設計書が表示されます。"))

    # 旧保存ボタンセクションは完全に削除されました。

if __name__ == "__main__":
    if "codebase_path" not in st.session_state:
        st.session_state.codebase_path = ""
    if "analysis_results_text" not in st.session_state:
        st.session_state.analysis_results_text = ""
    if "api_documents" not in st.session_state: 
        st.session_state.api_documents = {}
    if "db_document" not in st.session_state:
        st.session_state.db_document = ""
    if "project_overview_text" not in st.session_state:
        st.session_state.project_overview_text = ""
    if "documents_generated" not in st.session_state: 
        st.session_state.documents_generated = False
    main() 