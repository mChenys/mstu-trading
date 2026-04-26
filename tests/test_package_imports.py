import importlib
import unittest


class PackageImportSmokeTest(unittest.TestCase):
    def test_package_namespaces_are_importable(self) -> None:
        modules = [
            "mstu_trading",
            "mstu_trading.strategy",
            "mstu_trading.backtest",
            "mstu_trading.market_data",
            "mstu_trading.trading",
            "mstu_trading.integrations",
            "mstu_trading.web",
            "mstu_trading.storage",
            "mstu_trading.app_runtime",
            "mstu_trading.config",
            "mstu_trading.strategy.fee_model",
            "mstu_trading.strategy.indicators",
            "mstu_trading.strategy.indicators_enhanced",
            "mstu_trading.strategy.realtime",
            "mstu_trading.backtest.engine",
            "mstu_trading.backtest.optimize",
            "mstu_trading.storage.sqlite_storage",
            "mstu_trading.market_data.store",
            "mstu_trading.market_data.fetcher",
            "mstu_trading.integrations.feishu_gateway",
            "mstu_trading.integrations.scheduler",
            "mstu_trading.integrations.webhook_worker",
            "mstu_trading.integrations.webhook_daemon",
            "mstu_trading.web.dashboard_service",
            "mstu_trading.web.app",
        ]

        for module_name in modules:
            with self.subTest(module=module_name):
                imported = importlib.import_module(module_name)
                self.assertIsNotNone(imported)
