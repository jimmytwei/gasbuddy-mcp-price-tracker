import argparse
import sys

from fastmcp import FastMCP
import gas_tool

# Initialize FastMCP Server
mcp = FastMCP("GasBuddy Service")


@mcp.tool()
async def search_gas_prices(location: str, fuel_type: str = "regular") -> str:
    """
    Finds the cheapest gas stations in a given city or zip code.

    Args:
        location: City name or 5-digit zip code (e.g., 'New York, NY' or '10001').
        fuel_type: Type of fuel (regular, midgrade, premium, diesel).
    """
    # Call the scraper module
    results = await gas_tool.get_cheapest_gas(location, fuel_type)

    if not results:
        return (
            f"No gas prices found for {location}. "
            "The location might be invalid or the service is down."
        )

    # Format the response as a clean string for the LLM
    output = [f"Cheapest {fuel_type} gas in {location}:"]
    for i, res in enumerate(results, 1):
        cash_str = " (Cash Price)" if res['is_cash'] else ""
        output.append(f"{i}. ${res['price']:.2f}{cash_str}")
        output.append(f"   Station: {res['station']}")
        output.append(f"   Address: {res['address']}\n")

    return "\n".join(output)


if __name__ == "__main__":
    mcp.run()
