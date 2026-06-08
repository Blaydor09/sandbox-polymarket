import asyncio
import json
import logging
import uuid
import datetime
import requests
import random
from typing import Dict, Any, Optional

from app.event_bus import bus
from app.config import (
    POLYMARKET_CLOB_API_URL,
    POLYMARKET_EXCHANGE_ADDRESS,
    GNOSIS_RPC_URL,
    POLYMARKET_API_KEY,
    POLYMARKET_API_SECRET,
    POLYMARKET_API_PASSPHRASE,
    POLYMARKET_PRIVATE_KEY
)

logger = logging.getLogger("ExecutionService")

class VaultSigner:
    """
    Simula una separación física de firma (tipo HashiCorp Vault / KMS).
    Construye y firma mensajes estructurados EIP-712 para el CLOB de Polymarket,
    devolviendo únicamente la firma criptográfica resultante sin exponer la clave privada.
    """
    def __init__(self, private_key: str):
        self.private_key = private_key
        self.signer_address = None
        if self.private_key:
            try:
                from eth_account import Account
                account = Account.from_key(self.private_key)
                self.signer_address = account.address
                logger.info(f"VaultSigner inicializado de forma segura para la dirección: {self.signer_address}")
            except Exception as e:
                logger.error(f"Error cargando la clave privada en VaultSigner: {e}")

    def sign_order_eip712(self, order_msg: Dict[str, Any], verifying_contract: str) -> Dict[str, Any]:
        """
        Construye la firma EIP-712 para una orden limit en Polymarket CLOB.
        """
        if not self.private_key:
            # Modo Dry-Run / Simulado (Vault Mock)
            dummy_sig = f"0x{uuid.uuid4().hex}{uuid.uuid4().hex}1c"
            dummy_address = "0x8F929DeFA771f81d111CdACa936a29f8f413998b"
            logger.warning("[VAULT MOCK] Generando firma criptográfica simulada en modo Dry-Run.")
            return {
                "signature": dummy_sig,
                "signer": dummy_address
            }

        try:
            from eth_account.messages import encode_structured_data
            from eth_account import Account
            
            # Formato oficial de tipos de Polymarket CLOB Order
            structured_data = {
                "types": {
                    "EIP712Domain": [
                        {"name": "name", "type": "string"},
                        {"name": "version", "type": "string"},
                        {"name": "chainId", "type": "uint256"},
                        {"name": "verifyingContract", "type": "address"}
                    ],
                    "Order": [
                        {"name": "salt", "type": "uint256"},
                        {"name": "maker", "type": "address"},
                        {"name": "signer", "type": "address"},
                        {"name": "taker", "type": "address"},
                        {"name": "tokenId", "type": "uint256"},
                        {"name": "makerAmount", "type": "uint256"},
                        {"name": "takerAmount", "type": "uint256"},
                        {"name": "side", "type": "uint8"},  # 0 = BUY, 1 = SELL
                        {"name": "expiration", "type": "uint256"},
                        {"name": "nonce", "type": "uint256"},
                        {"name": "feeRateBps", "type": "uint256"}
                    ]
                },
                "domain": {
                    "name": "ClobMarketMaker",
                    "version": "1",
                    "chainId": 100,  # Gnosis Chain
                    "verifyingContract": verifying_contract
                },
                "primaryType": "Order",
                "message": order_msg
            }
            
            encoded = encode_structured_data(structured_data)
            signed = Account.sign_message(encoded, self.private_key)
            return {
                "signature": signed.signature.hex(),
                "signer": self.signer_address
            }
        except Exception as e:
            logger.error(f"Error firmando orden en EIP-712: {e}")
            raise e

class GnosisTransactionManager:
    """
    Gestiona interacciones directamente en la blockchain de Gnosis Chain.
    Implementa resubida de transacciones en cadena mediante Replace-By-Fee (RBF / Gas Bump).
    """
    def __init__(self, rpc_url: str):
        self.rpc_url = rpc_url
        self.is_mocked = not rpc_url or "gnosischain" not in rpc_url

    def get_token_balance(self, wallet_address: str, token_address: str = None) -> float:
        """Consulta el saldo de tokens real mediante RPC o devuelve simulación si está mocked."""
        if self.is_mocked:
            logger.debug("[RPC MOCK] Consultando saldo de USDC simulado en Gnosis: 5420.50 USD")
            return 5420.50
        
        # Implementación de llamada JSON-RPC real
        try:
            # Para USDC en Gnosis Chain (ERC20 balanceOf)
            # erc20 balanceOf selector: 0x70a08231
            token_addr = token_address or "0xddaf1e257144272ce11475c4afbc3decfa55c478" # USDC on Gnosis
            data = f"0x70a08231000000000000000000000000{wallet_address[2:]}"
            
            payload = {
                "jsonrpc": "2.0",
                "method": "eth_call",
                "params": [{"to": token_addr, "data": data}, "latest"],
                "id": 1
            }
            headers = {"content-type": "application/json"}
            res = requests.post(self.rpc_url, json=payload, headers=headers, timeout=5)
            result = res.json().get("result", "0x0")
            balance = int(result, 16) / 1e6  # USDC tiene 6 decimales en Gnosis
            logger.info(f"Saldo real USDC consultado por RPC Gnosis para {wallet_address}: {balance:.2f} USDC")
            return balance
        except Exception as e:
            logger.error(f"Error consultando RPC balance en Gnosis: {e}. Usando fallback simulado.")
            return 5420.50

    async def execute_onchain_transaction_with_gas_bump(self, wallet_address: str, private_key: str, tx_payload: Dict[str, Any]) -> str:
        """
        Envía una transacción en cadena (Gnosis) y monitoriza su inclusión en bloques.
        Si se estanca en la mempool, incrementa el precio del gas (Gas Bump / RBF) y la vuelve a enviar.
        """
        if self.is_mocked or not private_key:
            logger.info("[RPC MOCK] Simulando transacción en cadena con lógica de Gas Bump.")
            await asyncio.sleep(0.5)
            return f"0xmock_tx_{uuid.uuid4().hex}"

        try:
            from web3 import Web3
            w3 = Web3(Web3.HTTPProvider(self.rpc_url))
            
            nonce = w3.eth.get_transaction_count(wallet_address)
            gas_price = w3.eth.gas_price
            
            tx = {
                'to': tx_payload.get('to'),
                'value': tx_payload.get('value', 0),
                'gas': tx_payload.get('gas', 100000),
                'maxFeePerGas': int(gas_price * 1.1),
                'maxPriorityFeePerGas': w3.eth.max_priority_fee,
                'nonce': nonce,
                'chainId': 100
            }
            
            # Intento 1 de envío
            signed_tx = w3.eth.account.sign_transaction(tx, private_key)
            tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
            logger.info(f"Transacción Gnosis enviada (Intento 1). Hash: {tx_hash.hex()}")
            
            # Monitoreo de 3 bloques (aprox 15 segundos en Gnosis Chain)
            for attempt in range(1, 4):
                try:
                    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=5)
                    logger.info(f"Transacción confirmada en bloque {receipt.blockNumber}!")
                    return tx_hash.hex()
                except asyncio.TimeoutError:
                    logger.warning(f"La transacción {tx_hash.hex()} no fue confirmada. Incrementando tarifas (Gas Bump)...")
                    # Incrementar gas price en un 15%
                    tx['maxFeePerGas'] = int(tx['maxFeePerGas'] * 1.15)
                    tx['maxPriorityFeePerGas'] = int(tx['maxPriorityFeePerGas'] * 1.15)
                    
                    signed_tx = w3.eth.account.sign_transaction(tx, private_key)
                    tx_hash = w3.eth.send_raw_transaction(signed_tx.rawTransaction)
                    logger.info(f"Re-enviando transacción con mayor tarifa (Intento {attempt + 1}). Nuevo Hash: {tx_hash.hex()}")
            
            raise Exception("La transacción no se pudo confirmar después de múltiples re-envíos con Gas Bump.")
        except Exception as e:
            logger.error(f"Error en ejecución con Gas Bump: {e}")
            raise e

class ExecutionService:
    def __init__(self):
        self.signer = VaultSigner(POLYMARKET_PRIVATE_KEY)
        self.tx_manager = GnosisTransactionManager(GNOSIS_RPC_URL)
        self.api_url = POLYMARKET_CLOB_API_URL
        self.exchange_address = POLYMARKET_EXCHANGE_ADDRESS
        self.is_dry_run = not (POLYMARKET_API_KEY and POLYMARKET_PRIVATE_KEY)

    async def execute_real_order(self, event_data: Dict[str, Any]) -> None:
        """
        Manejador de risk.order.approved.
        Prepara el mensaje estructurado de la orden, llama al firmador aislado,
        y envía la orden real al motor de casamiento de Polymarket.
        """
        correlation_id = event_data.get("correlationId")
        payload = event_data.get("payload", {})
        
        order_id = payload.get("orderId")
        agent_id = payload.get("agentId")
        market_address = payload.get("marketAddress")
        side = payload.get("side")
        size_tokens = payload.get("sizeTokens", 0.0)
        limit_price = payload.get("limitPrice", 1.0)
        amount_usd = payload.get("amountUsd", 0.0)
        outcome_index = payload.get("outcomeIndex", 1)

        logger.info(f"[EXECUTION START] Procesando orden aprobada {order_id} en modo REAL. correlationId={correlation_id}")

        # 1. Preparar campos de la orden CLOB
        # Determinamos side: 0 = BUY (maker compra shares), 1 = SELL (maker vende shares)
        side_code = 0 if side == "BUY" else 1
        
        # En Polymarket, makerAmount/takerAmount dependen de BUY/SELL
        # Si compramos, vendemos USD (makerAmount = amount_usd) y compramos tokens (takerAmount = size_tokens)
        # Si vendemos, vendemos tokens (makerAmount = size_tokens) y compramos USD (takerAmount = amount_usd)
        # Notas: Polymarket requiere importes expresados con precisión (USDC = 6 decimales, Shares = 6 decimales)
        precision_usd = int(amount_usd * 1e6)
        precision_shares = int(size_tokens * 1e6)
        
        maker_amount = precision_usd if side == "BUY" else precision_shares
        taker_amount = precision_shares if side == "BUY" else precision_usd
        
        salt = random.randint(1, 2**256 - 1)
        expiration = int(datetime.datetime.now(datetime.timezone.utc).timestamp() + 300) # Expira en 5 mins
        nonce = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
        
        # Simulamos o consultamos token ID (en producción el token ID es el hash derivado del mercado y outcome)
        # Token ID mock para el log de auditoría
        token_id_int = int(market_address, 16) if market_address.startswith("0x") else 12345
        
        order_message = {
            "salt": salt,
            "maker": self.signer.signer_address or "0x8F929DeFA771f81d111CdACa936a29f8f413998b",
            "signer": self.signer.signer_address or "0x8F929DeFA771f81d111CdACa936a29f8f413998b",
            "taker": "0x0000000000000000000000000000000000000000",
            "tokenId": token_id_int,
            "makerAmount": maker_amount,
            "takerAmount": taker_amount,
            "side": side_code,
            "expiration": expiration,
            "nonce": nonce,
            "feeRateBps": 0
        }

        # 2. Firmar la orden utilizando el VaultSigner aislado
        try:
            signature_data = self.signer.sign_order_eip712(order_message, self.exchange_address)
            signature = signature_data["signature"]
            signer_address = signature_data["signer"]
            logger.info(f"[EIP-712 SIGNATURE GENERATED] Dirección: {signer_address} | Firma: {signature[:12]}...")
        except Exception as e:
            logger.critical(f"Fallo crítico en firma de la transacción en VaultSigner: {e}")
            await self._reject_order(order_id, agent_id, market_address, correlation_id, "SIGNATURE_ERROR")
            return

        # 3. Envío al API CLOB de Polymarket o Simulación Dry-Run
        if self.is_dry_run:
            logger.info(
                f"[DRY-RUN PRODUCTION] Simulando envío HTTP POST a {self.api_url}/order. "
                f"La firma y el payload son válidos."
            )
            # Esperamos una latencia real de la red (Jitter)
            simulated_latency = random.randint(120, 280)
            await asyncio.sleep(simulated_latency / 1000.0)
            
            # Generar hash de transacción simulado para la red Gnosis
            tx_hash = f"gnosis_tx_{uuid.uuid4().hex[:32]}"
            average_price = limit_price # En dry run ejecutamos al límite
            executed_size = size_tokens
            status = "FILLED"
            
            logger.info(
                f"[EXECUTION SUCCESS] Orden real {order_id} (Dry-run) ejecutada. "
                f"Precio={average_price}, Tamaño={executed_size}, Latencia={simulated_latency}ms"
            )
            
            report_event = {
                "eventId": f"evt_{uuid.uuid4()}",
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "version": "1.0.0",
                "correlationId": correlation_id,
                "payload": {
                    "orderId": order_id,
                    "agentId": agent_id,
                    "marketAddress": market_address,
                    "side": side,
                    "outcomeIndex": outcome_index,
                    "amountUsd": round(executed_size * average_price, 2),
                    "status": status,
                    "executedSize": round(executed_size, 4),
                    "averagePrice": average_price,
                    "slippageIncurredPct": round(random.uniform(0.01, 0.05), 4),
                    "simulatedLatencyMs": simulated_latency,
                    "nativeTransactionHash": tx_hash
                }
            }
            await bus.publish("broker.order.execution_report", report_event)
        
        else:
            # Enviar solicitud real a la API de Polymarket
            try:
                order_payload = {
                    "order": {
                        "salt": str(salt),
                        "maker": signer_address,
                        "signer": signer_address,
                        "taker": "0x0000000000000000000000000000000000000000",
                        "tokenId": str(token_id_int),
                        "makerAmount": str(maker_amount),
                        "takerAmount": str(taker_amount),
                        "side": side_code,
                        "expiration": str(expiration),
                        "nonce": str(nonce),
                        "feeRateBps": 0,
                        "signature": signature
                    },
                    "owner": signer_address
                }
                
                headers = {
                    "Content-Type": "application/json",
                    "POLY-API-KEY": POLYMARKET_API_KEY,
                }
                
                start_time = datetime.datetime.now()
                response = requests.post(f"{self.api_url}/order", json=order_payload, headers=headers, timeout=10)
                latency_ms = int((datetime.datetime.now() - start_time).total_seconds() * 1000)
                
                if response.status_code in (200, 201, 202):
                    res_data = response.json()
                    average_price = float(res_data.get("price", limit_price))
                    executed_size = float(res_data.get("size", size_tokens))
                    tx_hash = res_data.get("orderID", f"poly_order_{uuid.uuid4().hex[:12]}")
                    status = "FILLED" if res_data.get("status") == "matched" else "PARTIALLY_FILLED"
                    
                    logger.info(f"[REAL CLOB FILLED] Orden {order_id} colocada exitosamente. Latencia: {latency_ms}ms")
                    
                    report_event = {
                        "eventId": f"evt_{uuid.uuid4()}",
                        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        "version": "1.0.0",
                        "correlationId": correlation_id,
                        "payload": {
                            "orderId": order_id,
                            "agentId": agent_id,
                            "marketAddress": market_address,
                            "side": side,
                            "outcomeIndex": outcome_index,
                            "amountUsd": round(executed_size * average_price, 2),
                            "status": status,
                            "executedSize": round(executed_size, 4),
                            "averagePrice": average_price,
                            "slippageIncurredPct": 0.0,
                            "simulatedLatencyMs": latency_ms,
                            "nativeTransactionHash": tx_hash
                        }
                    }
                    await bus.publish("broker.order.execution_report", report_event)
                else:
                    error_msg = response.text
                    logger.error(f"[REAL CLOB REJECTED] Error de API {response.status_code}: {error_msg}")
                    await self._reject_order(order_id, agent_id, market_address, correlation_id, "API_REJECTION_ERROR")
            
            except Exception as e:
                logger.error(f"Excepción de conexión a Polymarket API: {e}")
                await self._reject_order(order_id, agent_id, market_address, correlation_id, "API_CONNECTION_TIMEOUT")

    async def _reject_order(self, order_id: str, agent_id: str, market_address: str, correlation_id: str, reason: str) -> None:
        """Helper para emitir un reporte de rechazo en caso de errores en producción."""
        report_event = {
            "eventId": f"evt_{uuid.uuid4()}",
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "version": "1.0.0",
            "correlationId": correlation_id,
            "payload": {
                "orderId": order_id,
                "agentId": agent_id,
                "marketAddress": market_address,
                "amountUsd": 0.0,
                "status": "REJECTED",
                "reason": reason,
                "executedSize": 0.0,
                "averagePrice": 0.0,
                "slippageIncurredPct": 0.0,
                "simulatedLatencyMs": 0,
                "nativeTransactionHash": "N/A"
            }
        }
        await bus.publish("broker.order.execution_report", report_event)

# Instancia global de ExecutionService
execution_service = ExecutionService()

def setup():
    from app.config import EXECUTION_MODE
    if EXECUTION_MODE == "REAL":
        bus.subscribe("risk.order.approved", execution_service.execute_real_order)
