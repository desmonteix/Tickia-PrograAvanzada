from abc import ABC, abstractmethod
import os

class PaymentProvider(ABC):
    @abstractmethod
    def create_checkout_session(self, ticket_id: str, amount: float, seller_account_id: str, platform_fee: float) -> str:
        """Returns the URL for the hosted checkout page"""
        pass
        
    @abstractmethod
    def release_funds_to_seller(self, charge_id: str):
        """Liberar el escrow al vendedor"""
        pass
        
    @abstractmethod
    def refund_buyer(self, charge_id: str):
        """Reembolso al comprador (ej: cancelación de evento)"""
        pass

class CulqiProvider(PaymentProvider):
    def __init__(self):
        self.public_key = os.getenv("CULQI_PUBLIC_KEY")
        self.private_key = os.getenv("CULQI_PRIVATE_KEY")
        
    def create_checkout_session(self, ticket_id: str, amount: float, seller_account_id: str, platform_fee: float) -> str:
        # En una integración real de Culqi se llama a /orders o se usa el checkout.js.
        # Aquí mockeamos la respuesta para devolver una URL simulada de la hosted page
        # y demostramos el flujo de marketplace split.
        return f"https://checkout.culqi.com/mock?ticket={ticket_id}&amount={amount}"
        
    def release_funds_to_seller(self, charge_id: str):
        # Llamar a Culqi API para confirmar la transferencia al seller
        return True
        
    def refund_buyer(self, charge_id: str):
        # Llamar a Culqi API para ejecutar el refund
        return True

# Factory
def get_payment_provider() -> PaymentProvider:
    # Retorna el proveedor configurado (Culqi en el piloto)
    return CulqiProvider()
