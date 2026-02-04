"""
ArXiv Paper Discovery MCP Server - Using ArXivXplorer API with Semantic Search

Source:
- https://gptstore.ai/gpts/vUPoYY1pm7-arxiv-xplorer/actions
- https://github.com/tan-yong-sheng/arxiv-semantic-search-mcp/tree/main


"""

import logging
import time
import re
import requests
import threading
from typing import List, Optional
from pydantic import BaseModel, Field
from mcp.server import FastMCP

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


# Custom exceptions
class ArxivSearchError(Exception):
    """Base exception for ArXiv search operations"""

    pass


class ArxivAPIError(ArxivSearchError):
    """API communication error"""

    pass


class ArxivPaperNotFound(ArxivSearchError):
    """Requested paper not found"""

    pass


# Initialize FastMCP server
mcp = FastMCP("ArXiv Discovery")

# ============================================================================
# Configuration Constants
# ============================================================================

# Rate limiting: Reasonable delay between requests
RATE_LIMIT_SECONDS = 1
last_request_time = [time.time()]  # Use list to allow modification in nested function
rate_limit_lock = threading.Lock()  # Thread-safe rate limiting

# ArXivXplorer API base URL
ARXIV_XPLORER_BASE = "https://search.arxivxplorer.com"

# Initialize session for connection pooling
session = requests.Session()

# Pre-compile regex pattern for better performance
ARXIV_ID_PATTERN = re.compile(r"(\d{4}\.\d{4,5}(?:v\d+)?)")


# ============================================================================
# Data Models
# ============================================================================


class ArxivPaper(BaseModel):
    """Model for ArXiv paper search results from ArXivXplorer"""

    id: str = Field(..., description="ArXiv paper ID (e.g., 2301.12345)")
    title: str = Field(..., description="Paper title")
    authors: List[str] = Field(..., description="List of paper authors")
    abstract: str = Field(..., description="Paper abstract/summary")
    published: str = Field(..., description="Publication date (ISO 8601 format)")
    categories: List[str] = Field(
        ..., description="ArXiv categories (e.g., ['cs.AI', 'cs.LG'])"
    )
    arxiv_url: str = Field(..., description="Direct link to the paper on ArXiv")
    pdf_url: str = Field(..., description="Direct link to the paper's PDF")
    relevance_score: Optional[float] = Field(
        None, description="Semantic relevance score (0-1)"
    )


# ============================================================================
# Utility Functions
# ============================================================================


def _validate_search_params(query: str, limit: int) -> None:
    """
    Validate search parameters.

    Args:
        query: Search query string
        limit: Maximum number of results

    Raises:
        ValueError: If parameters are invalid
    """
    if not query or not query.strip():
        raise ValueError("Query cannot be empty")

    if limit < 1 or limit > 100:
        raise ValueError("Limit must be between 1 and 100")


def rate_limit_request():
    """Enforce rate limiting to be respectful to the API (thread-safe)"""
    with rate_limit_lock:
        elapsed = time.time() - last_request_time[0]
        if elapsed < RATE_LIMIT_SECONDS:
            time.sleep(RATE_LIMIT_SECONDS - elapsed)
        last_request_time[0] = time.time()
        logger.debug("Rate limit enforced")


def extract_arxiv_id(url: str) -> Optional[str]:
    """
    Extract ArXiv paper ID from URL.
    Handles formats like:
    - https://arxiv.org/abs/2301.12345
    - https://arxiv.org/pdf/2301.12345
    - 2301.12345
    """
    match = ARXIV_ID_PATTERN.search(url)
    return match.group(1) if match else None


def _get_paper_id_base(paper_id: str) -> str:
    """
    Extract base paper ID without version number.

    Args:
        paper_id: Paper ID potentially with version (e.g., '2301.12345v1' or '2301.12345')

    Returns:
        Paper ID base without version
    """
    return paper_id.split("v")[0] if "v" in paper_id else paper_id


def format_paper_result(raw_paper: dict) -> ArxivPaper:
    """
    Convert ArXivXplorer API response to ArxivPaper model.

    Args:
        raw_paper: Raw paper object from ArXivXplorer API

    Returns:
        ArxivPaper object with all fields properly formatted
    """
    paper_id = raw_paper.get("id", "")
    logger.debug(f"Formatting paper result: {paper_id}")

    # Parse authors from comma-separated string
    authors_str = raw_paper.get("authors", "")
    authors = (
        [a.strip() for a in authors_str.split(",") if a.strip()] if authors_str else []
    )

    # Extract date in ISO format
    date_str = raw_paper.get("date", "")
    if date_str:
        # Extract just the date part (YYYY-MM-DD)
        published = date_str[:10]
    else:
        published = "Unknown"

    # Get categories
    categories = raw_paper.get("categories", [])
    if isinstance(categories, str):
        categories = [c.strip() for c in categories.split(",")]

    # Get relevance score if available
    relevance_score = raw_paper.get("score")

    return ArxivPaper(
        id=paper_id,
        title=raw_paper.get("title", "Unknown"),
        authors=authors,
        abstract=raw_paper.get("abstract", "No abstract available"),
        published=published,
        categories=categories,
        arxiv_url=f"https://arxiv.org/abs/{paper_id}",
        pdf_url=f"https://arxiv.org/pdf/{paper_id}.pdf",
        relevance_score=relevance_score,
    )


# ============================================================================
# Core API Functions
# ============================================================================


def _build_search_params(
    query: str,
    categories: Optional[List[str]] = None,
    years: Optional[List[int]] = None,
    page: int = 1,
) -> dict:
    """
    Build query parameters for ArXivXplorer API.

    Args:
        query: Search query string
        categories: Optional list of arxiv categories to filter by
        years: Optional list of years to filter by
        page: Page number for pagination

    Returns:
        Dictionary of query parameters
    """
    params = {
        "q": query,
        "page": page,
        "method": "semantic",  # Use semantic search for better results
    }

    # Add categories filter if provided
    if categories:
        params["cats"] = ",".join(categories)
        logger.debug(f"Added category filter: {categories}")

    # Add years filter if provided
    if years:
        # Use only the first year - the API seems to have issues with multiple years
        # Note: The API may not support future years (e.g., 2025, 2026), but we'll try
        params["year"] = str(years[0])
        logger.debug(f"Added year filter: {years[0]}")

    return params


def _fetch_from_arxiv_api(params: dict) -> list:
    """
    Make HTTP request to ArXivXplorer API.

    Args:
        params: Query parameters

    Returns:
        JSON response as a list

    Raises:
        ArxivAPIError: If API request fails
    """
    try:
        logger.debug(f"Querying ArXivXplorer API with params: {params}")
        response = session.get(
            ARXIV_XPLORER_BASE,
            params=params,
            timeout=10,
            headers={"User-Agent": "arxiv-discovery-mcp/2.0"},
        )
        response.raise_for_status()

        raw_papers = response.json()
        logger.debug(f"Received {len(raw_papers)} papers from API")
        return raw_papers

    except requests.RequestException as e:
        logger.error(f"API request failed: {str(e)}")
        raise ArxivAPIError(f"Failed to query ArXivXplorer API: {str(e)}")
    except ValueError as e:
        logger.error(f"Failed to parse API response: {str(e)}")
        raise ArxivAPIError(f"Failed to parse ArXivXplorer response: {str(e)}")


def _parse_arxiv_response(raw_papers: list, limit: int) -> List[ArxivPaper]:
    """
    Parse API response and convert to ArxivPaper objects.

    Args:
        raw_papers: Raw JSON response from API
        limit: Maximum number of papers to return

    Returns:
        List of ArxivPaper objects
    """
    papers = []
    for raw_paper in raw_papers[:limit]:
        try:
            paper = format_paper_result(raw_paper)
            papers.append(paper)
        except Exception as e:
            # Skip malformed entries
            logger.warning(f"Skipping malformed paper entry: {str(e)}")
            continue

    logger.debug(f"Successfully parsed {len(papers)} papers")
    return papers


def query_arxiv_xplorer(
    query: str,
    categories: Optional[List[str]] = None,
    years: Optional[List[int]] = None,
    page: int = 1,
    limit: int = 10,
) -> List[ArxivPaper]:
    """
    Query the ArXivXplorer API with semantic search capabilities.

    Args:
        query: Search query string (supports semantic search)
        categories: Optional list of arxiv categories to filter by (e.g., ['cs.AI', 'cs.LG'])
        years: Optional list of years to filter by (should be historical years, e.g., 2020-2024)
        page: Page number for pagination (starts from 1)
        limit: Maximum number of results to return

    Returns:
        List of ArxivPaper objects
    """
    rate_limit_request()

    # Build query parameters
    params = _build_search_params(query, categories, years, page)

    # Fetch and parse results
    raw_papers = _fetch_from_arxiv_api(params)
    papers = _parse_arxiv_response(raw_papers, limit)

    return papers


# ============================================================================
# Reference Paper Fetching (for similar paper search)
# ============================================================================


def _fetch_reference_paper(paper_id_base: str) -> ArxivPaper:
    """
    Fetch the reference paper from ArXiv with fallback strategies.

    Args:
        paper_id_base: Base paper ID without version

    Returns:
        ArxivPaper object

    Raises:
        ArxivPaperNotFound: If paper cannot be found
    """
    try:
        logger.debug(f"Fetching reference paper: {paper_id_base}")
        reference_papers = query_arxiv_xplorer(query=paper_id_base, page=1, limit=5)

        # Find exact match by ID
        reference_paper = None
        for paper in reference_papers:
            paper_id_base_from_result = _get_paper_id_base(paper.id)
            if paper_id_base_from_result == paper_id_base:
                reference_paper = paper
                logger.debug(f"Found exact match: {paper.id}")
                break

        if not reference_paper and reference_papers:
            # If exact match not found but we got results, use the first one
            reference_paper = reference_papers[0]
            logger.debug(f"Using first result as reference: {reference_paper.id}")

        if reference_paper:
            return reference_paper

    except ArxivSearchError:
        logger.warning(f"Failed to fetch reference paper: {paper_id_base}")

    # No paper found
    raise ArxivPaperNotFound(f"Paper not found on ArXiv: {paper_id_base}")


def _search_and_filter_similar(
    reference_paper: ArxivPaper,
    limit: int,
    years: Optional[List[int]] = None,
) -> List[ArxivPaper]:
    """
    Search for papers similar to reference paper and filter out the original.

    Args:
        reference_paper: The reference paper to find similar papers for
        limit: Maximum number of similar papers to return
        years: Optional list of years to filter by

    Returns:
        List of similar papers (excluding the original)
    """
    logger.debug(f"Searching for papers similar to: {reference_paper.title}")

    # Use the paper's full title as the primary search query for better semantic matching
    search_query = reference_paper.title

    similar_papers = query_arxiv_xplorer(
        query=search_query,
        categories=None,
        years=years,
        page=1,
        limit=limit + 1,  # Request extra to account for filtering out the original
    )

    if not similar_papers:
        logger.debug("No similar papers found")
        return []

    # Filter out the reference paper itself
    original_paper_id_base = _get_paper_id_base(reference_paper.id)
    filtered_papers = [
        paper
        for paper in similar_papers
        if _get_paper_id_base(paper.id) != original_paper_id_base
    ]

    logger.debug(f"Found {len(filtered_papers)} similar papers after filtering")
    return filtered_papers[:limit]


# ============================================================================
# MCP Tool Endpoints
# ============================================================================


@mcp.tool()
def search_arxiv_papers(
    query: str,
    limit: int = 10,
    years: Optional[int | List[int]] = None,
) -> List[ArxivPaper]:
    """
    Search ArXiv papers using semantic search with ArXivXplorer API.

    Supports natural language queries for finding relevant research papers.

    Args:
        query: Search query (supports natural language for semantic search, e.g., 'neural networks for image classification')
        limit: Maximum number of results to return (default: 10, max: 100)
        years: Optional year or list of years to filter by (e.g., 2025 or [2024, 2025])

    Returns:
        List of ArxivPaper objects sorted by relevance
    """
    _validate_search_params(query, limit)

    # Convert single year to list
    years_list = None
    if years is not None:
        years_list = [years] if isinstance(years, int) else years

    try:
        logger.info(
            f"Searching ArXiv for: {query} (limit: {limit}, years: {years_list})"
        )

        try:
            papers = query_arxiv_xplorer(
                query=query, categories=None, years=years_list, page=1, limit=limit
            )
        except ArxivAPIError as e:
            if years_list:
                logger.warning(
                    "Year-filtered search failed; retrying without year filter. "
                    f"(years={years_list}, error={e})"
                )
                papers = query_arxiv_xplorer(
                    query=query, categories=None, years=None, page=1, limit=limit
                )
            else:
                raise

        logger.info(f"Found {len(papers)} papers")
        return papers

    except ArxivSearchError:
        raise
    except Exception as e:
        logger.error(f"Error searching ArXiv: {str(e)}")
        raise RuntimeError(f"Error searching ArXiv: {str(e)}")


@mcp.tool()
def search_similar_papers(
    arxiv_url: str,
    limit: int = 10,
    years: Optional[int | List[int]] = None,
) -> List[ArxivPaper]:
    """
    Find papers similar to a given ArXiv paper using semantic search.

    Extracts the main topic from the reference paper and searches for related papers.

    Args:
        arxiv_url: ArXiv paper URL or paper ID (e.g., https://arxiv.org/abs/2301.12345 or 2301.12345)
        limit: Maximum number of similar papers to return (default: 10)
        years: Optional year or list of years to filter by (e.g., 2025 or [2024, 2025])

    Returns:
        List of ArxivPaper objects similar to the reference paper (excluding the original)
    """
    if not arxiv_url or not arxiv_url.strip():
        raise ValueError("ArXiv URL or paper ID cannot be empty")

    if limit < 1 or limit > 100:
        raise ValueError("Limit must be between 1 and 100")

    # Convert single year to list
    years_list = None
    if years is not None:
        years_list = [years] if isinstance(years, int) else years

    try:
        logger.info(
            f"Searching for papers similar to: {arxiv_url} (limit: {limit}, years: {years_list})"
        )

        # Extract paper ID
        paper_id = extract_arxiv_id(arxiv_url)
        if not paper_id:
            raise ValueError(f"Invalid ArXiv URL or paper ID: {arxiv_url}")

        # Remove version number for cleaner queries
        paper_id_base = _get_paper_id_base(paper_id)

        # Fetch the reference paper and find similar ones
        reference_paper = _fetch_reference_paper(paper_id_base)

        try:
            similar_papers = _search_and_filter_similar(reference_paper, limit, years_list)
        except ArxivAPIError as e:
            if years_list:
                logger.warning(
                    "Year-filtered similar-paper search failed; retrying without year filter. "
                    f"(years={years_list}, error={e})"
                )
                similar_papers = _search_and_filter_similar(reference_paper, limit, None)
            else:
                raise

        logger.info(f"Found {len(similar_papers)} similar papers")
        return similar_papers

    except ArxivSearchError:
        raise
    except ValueError:
        raise
    except Exception as e:
        logger.error(f"Error finding similar papers: {str(e)}")
        raise RuntimeError(f"Error finding similar papers: {str(e)}")


if __name__ == "__main__":
    mcp.run()
