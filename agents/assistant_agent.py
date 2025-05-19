import autogen
from typing import Optional, Dict, Any

class ConfigurableAssistantAgent(autogen.AssistantAgent):
    """
    設定ファイルからLLM構成を読み込むことができる AssistantAgent のカスタム版。
    """
    def __init__(self, name: str, llm_config: Optional[Dict[str, Any]] = None, system_message: Optional[str] = None, **kwargs):
        """
        コンストラクタ。

        Args:
            name (str): Agentの名前。
            llm_config (Optional[Dict[str, Any]]): Autogen形式のLLM設定。Noneの場合、デフォルト設定が試みられます。
            system_message (Optional[str]): Agentのシステムメッセージ。
            **kwargs: autogen.AssistantAgent に渡されるその他のキーワード引数。
        """
        if llm_config is None:
            # llm_configがNoneの場合、Autogenのデフォルト動作に任せるか、
            # ここで環境変数や特定の設定ファイルからロードするロジックを追加できます。
            # シンプルにするため、ここでは警告を出すか、基本的なフォールバックを設定します。
            print(f"警告: Agent '{name}' の llm_config が提供されていません。Autogenのデフォルト設定を使用します。")
            # llm_config = {"model": "gpt-3.5-turbo"} # 例: フォールバック

        super().__init__(
            name=name,
            llm_config=llm_config,
            system_message=system_message,
            **kwargs
        )

def get_llm_config_from_app(app_config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    アプリケーション設定辞書からAutogenに必要なLLM設定を抽出します。
    APIキーは環境変数 OPENAI_API_KEY から読み込まれることを想定しています。

    Args:
        app_config (Dict[str, Any]): ロードされた app_config.yaml の内容。

    Returns:
        Optional[Dict[str, Any]]: Autogen用のLLM設定辞書。または設定がない場合はNone。
    """
    if not app_config or 'llm_config' not in app_config:
        print("エラー: app_config に llm_config が見つかりません。")
        return None
    
    # app_configからllm_config部分を取得
    config = app_config.get('llm_config', {})
    
    # Autogenが期待する形式に合わせる
    # 主に model 名が必要。APIキーはAutogenが環境変数から読み取る。
    # もし config_list を使いたい場合は、以下のように整形する:
    # return {
    #     "config_list": [
    #         {
    #             "model": config.get("model"),
    #             # "api_key": os.environ.get("OPENAI_API_KEY") # Autogenが自動で処理するので不要
    #         }
    #     ],
    #     "temperature": config.get("temperature", 0.7), # 必要に応じて
    #     # "cache_seed": 42, # キャッシュを利用する場合
    # }
    # シンプルなケースでは、モデル名だけでも機能することがある
    if "model" not in config:
        print("エラー: llm_config に 'model' が指定されていません。")
        return None
        
    # Autogenの `llm_config` は直接モデル設定辞書か、config_list を持つ辞書を受け入れる
    # ここでは直接モデル設定辞書を返す (APIキーは環境変数から自動で使われる)
    return {
        "model": config.get("model"),
        # "api_key": os.environ.get("OPENAI_API_KEY"), # これを書くと明示的になるが、通常Autogenが処理
        "temperature": config.get("temperature", 0.7) # 例
    } 