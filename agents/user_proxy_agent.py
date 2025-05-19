import autogen
from typing import Dict, Any, Optional, Callable, Union

class StreamlitUserProxyAgent(autogen.UserProxyAgent):
    """
    Streamlitアプリケーションと連携するためのUserProxyAgentカスタム版。
    `human_input_mode` は通常 "NEVER" に設定し、Streamlit UIから対話を開始します。
    """
    def __init__(
        self,
        name: str,
        system_message: Optional[str] = "",
        human_input_mode: str = "NEVER", # Streamlitから操作するので基本NEVER
        code_execution_config: Optional[Union[Dict, bool]] = False, # 通常ユーザープロキシはコード実行しない
        **kwargs
    ):
        """
        コンストラクタ。

        Args:
            name (str): Agentの名前。
            system_message (Optional[str]): Agentのシステムメッセージ。
            human_input_mode (str): "NEVER", "TERMINATE", "ALWAYS" のいずれか。
                                    Streamlit連携の場合、通常は "NEVER"。
            code_execution_config (Optional[Union[Dict, bool]]): コード実行設定。デフォルトはFalse。
            **kwargs: autogen.UserProxyAgent に渡されるその他のキーワード引数。
        """
        super().__init__(
            name=name,
            system_message=system_message,
            human_input_mode=human_input_mode,
            code_execution_config=code_execution_config, 
            **kwargs
        )

    # Streamlit UIからのメッセージをAgentに送信したり、
    # Agentからの応答をStreamlit UIに表示したりするためのメソッドをここに追加できますが、
    # Autogenの基本的な initiate_chat / send / receive メカニズムを使用することが多いです。
    # このクラスは主に、UserProxyAgentの初期設定をStreamlit用に特化させる役割を持ちます。 