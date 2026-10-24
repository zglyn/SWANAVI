"""Master control loop for a finished trip plan.

The planner calls this package. Flight, hotel, attraction, email, and progress
capabilities stay in their own packages; this package only calls them.
"""

from booking.master.service import handle_payload, segment_accepted

__all__ = ["handle_payload", "segment_accepted"]
