import sys
from market_maker.utils import math, log
from market_maker.settings import settings
from market_maker.market_maker import OrderManager
from indexprice.indexprice import IndexPrice

logger = log.setup_custom_logger('custom')
offset = []


class CustomOrderManager(OrderManager):
    """A sample order manager for implementing your own custom strategy"""

    def place_orders(self) -> None:
        buy_orders = []
        sell_orders = []
        offset_cumul = 0
        offset_coef = 0

        # IndexPrice
        indexprice = IndexPrice().LastPrice()

        # BitMEX data
        ticker = self.exchange.get_ticker()

        # Offset
        offset.append(((ticker["mid"] - indexprice) / indexprice))
        if len(offset) > settings.OFFSET_MAX:
            del offset[0]

        # Calcul de l'offset à appliquer
        # On accorde plus d'importance aux données récentes selon certains settings
        for i in range(0, len(offset)):
            offset_cumul += (offset[i] * (2 ** i))
            offset_coef += (2 ** i)

        # Calcul offset final
        # On obtient un pourcentage brut à appliquer à notre indexprice
        offset_calcul = (offset_cumul / offset_coef)
        indexoffset = indexprice * (1 + offset_calcul)

        logger.debug('Taille Offset : ' + str(len(offset)))
        logger.debug(str(offset))
        logger.info('Offset calculé : ' + str(round(offset_calcul * 100,4)))
        logger.info('IndexPrice avec offset : ' + str(indexoffset))

        for i in range (0, settings.ORDER_PAIRS):
            buyprice1 = math.toNearest(indexoffset * (1 - (settings.INTERVAL * (i + 1) / 2)), self.instrument['tickSize'])
            buy_orders.append({'price': float(buyprice1), 'orderQty': (settings.ORDER_START_SIZE + (settings.ORDER_STEP_SIZE * i)), 'side': "Buy"})

            sellprice1 = math.toNearest(indexoffset * (1 + (settings.INTERVAL * (i + 1) / 2)), self.instrument['tickSize'])
            sell_orders.append({'price': float(sellprice1), 'orderQty': (settings.ORDER_START_SIZE + (settings.ORDER_STEP_SIZE * i)), 'side': "Sell"})

        # populate buy and sell orders, e.g.
        #buy_orders.append({'price': float(buyprice1), 'orderQty': 100, 'side': "Buy"})
        #sell_orders.append({'price': float(sellprice1), 'orderQty': 100, 'side': "Sell"})

        self.converge_orders(buy_orders, sell_orders)


def run() -> None:
    order_manager = CustomOrderManager()

    # Try/except just keeps ctrl-c from printing an ugly stacktrace
    try:
        order_manager.run_loop()
    except (KeyboardInterrupt, SystemExit):
        sys.exit()
