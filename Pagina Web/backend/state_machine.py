"""
Máquina de Estados para Entradas (Tickets).

Define explícitamente las transiciones válidas y rechaza con error cualquier
salto de estado no permitido, incluso si se intenta desde el código interno.

Grafo de estados:
    DISPONIBLE ──buy──► RESERVADA ──charge──► VENDIDA ──escrow_released──► LIBERADA
                │                   │
           (timeout)           (refund)
                │                   │
                └───────────────────┴──► REEMBOLSADA (terminal)
                        (LIBERADA es terminal)
"""
from .models import TicketState
from fastapi import HTTPException

# Transiciones válidas: { estado_actual: [estados_permitidos] }
VALID_TICKET_TRANSITIONS: dict[TicketState, list[TicketState]] = {
    TicketState.DISPONIBLE:  [TicketState.RESERVADA],
    TicketState.RESERVADA:   [TicketState.VENDIDA, TicketState.PENDIENTE_RENOMINACION, TicketState.DISPONIBLE],   # DISPONIBLE = timeout/liberación
    TicketState.PENDIENTE_RENOMINACION: [TicketState.VENDIDA, TicketState.REEMBOLSADA],
    TicketState.VENDIDA:     [TicketState.LIBERADA, TicketState.REEMBOLSADA],
    TicketState.LIBERADA:    [],   # Estado terminal — el dinero ya fue liberado
    TicketState.REEMBOLSADA: [],   # Estado terminal — el dinero fue reembolsado
}

def validate_ticket_transition(current_state: TicketState, new_state: TicketState) -> None:
    """
    Valida que la transición de estado sea legal según la máquina de estados.
    Lanza HTTPException 409 si la transición está prohibida.

    Uso:
        validate_ticket_transition(ticket.estado, TicketState.VENDIDA)
        ticket.estado = TicketState.VENDIDA  # Solo si la línea anterior no lanzó excepción
    """
    allowed = VALID_TICKET_TRANSITIONS.get(current_state, [])
    if new_state not in allowed:
        allowed_names = [s.value for s in allowed] if allowed else ["ninguno (estado terminal)"]
        raise HTTPException(
            status_code=409,
            detail=(
                f"Transición de estado inválida: '{current_state.value}' → '{new_state.value}'. "
                f"Desde '{current_state.value}' solo se permite: {allowed_names}."
            )
        )
