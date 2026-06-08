import os
import json
import logging
from typing import Dict, Any, Optional
from app.event_bus import bus
from app.config import PORTFOLIO_STATE_FILE, INITIAL_PORTFOLIO_USD

logger = logging.getLogger("PortfolioManager")

class PortfolioManager:
    def __init__(self):
        self.state_file = PORTFOLIO_STATE_FILE
        self.usd_balance = INITIAL_PORTFOLIO_USD
        # Formato: {market_address: {outcome_index: shares_count}}
        self.positions: Dict[str, Dict[str, float]] = {}
        self.load_state()

    def load_state(self) -> None:
        """Carga el estado de la cartera y posiciones de disco."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r") as f:
                    state = json.load(f)
                    self.usd_balance = state.get("usd_balance", INITIAL_PORTFOLIO_USD)
                    self.positions = state.get("positions", {})
                logger.info("Estado de cartera cargado exitosamente.")
            except Exception as e:
                logger.error(f"Error cargando estado de cartera: {e}")
                self.reset()
        else:
            self.reset()

    def save_state(self) -> None:
        """Persiste el estado actual de la cartera en disco."""
        try:
            state = {
                "usd_balance": round(self.usd_balance, 2),
                "positions": self.positions
            }
            with open(self.state_file, "w") as f:
                json.dump(state, f, indent=2)
        except Exception as e:
            logger.error(f"Error guardando estado de cartera: {e}")

    def reset(self) -> None:
        """Restablece la cartera a su estado inicial ($10,000 USD y sin posiciones)."""
        self.usd_balance = INITIAL_PORTFOLIO_USD
        self.positions = {}
        self.save_state()
        logger.info("Cartera de Paper Trading restablecida a valores iniciales.")

    def get_net_asset_value(self) -> float:
        """
        Calcula el Valor Neto de la Cartera (Net Asset Value - NAV).
        NAV = Saldo USD + Suma de (Acciones * Precio de Compra/Punta de Venta actual del mercado).
        """
        from app.broker import broker
        
        assets_value = 0.0
        for market, market_positions in self.positions.items():
            # Intentamos obtener el precio punta de venta del broker
            # Usamos bids[0][0] (el precio al que podemos vender de inmediato)
            market_ob = broker.mock_orderbooks.get(market)
            current_price = 0.50 # Precio default en Polymarket si no hay feed
            
            if market_ob and market_ob.get("bids"):
                current_price = market_ob["bids"][0][0]
                
            for outcome, shares in market_positions.items():
                # Nota: Si el outcome comprado es el outcome 0, su precio es (1.0 - precio_bids_outcome_1)
                # En este MVP asumimos que el precio punta aplica al outcome directo.
                assets_value += shares * current_price

        total_nav = round(self.usd_balance + assets_value, 2)
        logger.debug(f"Cálculo NAV: Balance USD={self.usd_balance}, Valor Activos={assets_value}, NAV={total_nav}")
        return total_nav

    def resolve_market(self, market_address: str, winning_outcome: int) -> Dict[str, Any]:
        """
        Liquida financieramente un mercado resuelto de Polymarket.
        * El outcome ganador paga $1.00 USD por cada token (share).
        * Los outcomes perdedores pagan $0.00 USD.
        """
        market_address = market_address.lower()
        if market_address not in self.positions:
            return {
                "status": "NO_POSITIONS",
                "message": f"No se encontraron posiciones activas para liquidar en el mercado {market_address}"
            }

        market_positions = self.positions[market_address]
        total_payout = 0.0
        details = {}

        # Evaluar cada outcome que posee el agente
        for outcome_str, shares in list(market_positions.items()):
            outcome_idx = int(outcome_str)
            if outcome_idx == winning_outcome:
                # El outcome ganador se liquida a $1.00 USD por share
                payout = shares * 1.00
                total_payout += payout
                details[outcome_str] = f"GANADOR: Liquidado {shares} shares a $1.00 -> +{payout:.2f} USD"
            else:
                details[outcome_str] = f"PERDEDOR: Liquidado {shares} shares a $0.00 -> 0.00 USD"

        # Acreditar fondos liquidados
        self.usd_balance += total_payout
        
        # Eliminar el mercado de las posiciones activas
        del self.positions[market_address]
        self.save_state()

        logger.info(
            f"[MARKET RESOLUTION] Mercado {market_address} resuelto con Outcome {winning_outcome}. "
            f"Pago total acreditado: {total_payout:.2f} USD."
        )

        return {
            "status": "RESOLVED",
            "marketAddress": market_address,
            "winningOutcome": winning_outcome,
            "payoutUsd": round(total_payout, 2),
            "newUsdBalance": round(self.usd_balance, 2),
            "details": details
        }

    async def handle_execution_report(self, event_data: Dict[str, Any]) -> None:
        """
        Manejador de broker.order.execution_report.
        Sincroniza en tiempo real los débitos y créditos del balance y las tenencias de tokens.
        """
        payload = event_data.get("payload", {})
        status = payload.get("status")
        
        if status not in ("FILLED", "PARTIALLY_FILLED"):
            return

        market_address = payload.get("marketAddress").lower()
        side = payload.get("side") # Propagado por broker
        outcome_idx = str(payload.get("outcomeIndex")) # Propagado por broker
        executed_size = payload.get("executedSize", 0.0)
        average_price = payload.get("averagePrice", 0.0)
        amount_usd = payload.get("amountUsd", 0.0)

        if side == "BUY":
            # Validar fondos suficientes en Paper Trading
            if self.usd_balance < amount_usd:
                logger.error(
                    f"Saldo de Paper Trading insuficiente para la ejecución de compra. "
                    f"Saldo: {self.usd_balance} USD. Requerido: {amount_usd} USD"
                )
                return
            
            # Debitar balance
            self.usd_balance -= amount_usd
            
            # Acreditar tokens
            if market_address not in self.positions:
                self.positions[market_address] = {}
            current_shares = self.positions[market_address].get(outcome_idx, 0.0)
            self.positions[market_address][outcome_idx] = round(current_shares + executed_size, 4)
            
            logger.info(
                f"[PAPER BUY] Cartera debitada: -{amount_usd:.2f} USD. "
                f"Acreditado: {executed_size} shares de {market_address} (outcome {outcome_idx})"
            )

        elif side == "SELL":
            # Validar tenencia de tokens suficiente
            market_pos = self.positions.get(market_address, {})
            current_shares = market_pos.get(outcome_idx, 0.0)
            
            if current_shares < executed_size:
                logger.error(
                    f"Posición insuficiente para vender tokens. "
                    f"Disponibles: {current_shares}. Requerido a vender: {executed_size}"
                )
                return
            
            # Acreditar balance
            self.usd_balance += amount_usd
            
            # Debitar tokens
            new_shares = round(current_shares - executed_size, 4)
            if new_shares <= 0:
                del self.positions[market_address][outcome_idx]
                if not self.positions[market_address]:
                    del self.positions[market_address]
            else:
                self.positions[market_address][outcome_idx] = new_shares
                
            logger.info(
                f"[PAPER SELL] Cartera acreditada: +{amount_usd:.2f} USD. "
                f"Debitado: {executed_size} shares de {market_address} (outcome {outcome_idx})"
            )

        # Persistir el estado modificado
        self.save_state()

# Instancia global del PortfolioManager
portfolio_manager = PortfolioManager()

def setup():
    bus.subscribe("broker.order.execution_report", portfolio_manager.handle_execution_report)
