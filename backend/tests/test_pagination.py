"""
Tests for pagination utility
"""
import pytest

from app.utils.pagination import calculate_pagination, PaginatedResponse


class TestCalculatePagination:
    """Test pagination calculation utility"""

    def test_first_page(self):
        """Test first page calculation"""
        result = calculate_pagination(total=100, page=1, page_size=20)
        assert result["offset"] == 0
        assert result["total_pages"] == 5
        assert result["has_next"] is True
        assert result["has_prev"] is False

    def test_middle_page(self):
        """Test middle page calculation"""
        result = calculate_pagination(total=100, page=3, page_size=20)
        assert result["offset"] == 40
        assert result["total_pages"] == 5
        assert result["has_next"] is True
        assert result["has_prev"] is True

    def test_last_page(self):
        """Test last page calculation"""
        result = calculate_pagination(total=100, page=5, page_size=20)
        assert result["offset"] == 80
        assert result["total_pages"] == 5
        assert result["has_next"] is False
        assert result["has_prev"] is True

    def test_empty_result(self):
        """Test empty result"""
        result = calculate_pagination(total=0, page=1, page_size=20)
        assert result["offset"] == 0
        assert result["total_pages"] == 0
        assert result["has_next"] is False
        assert result["has_prev"] is False

    def test_partial_last_page(self):
        """Test partial last page"""
        result = calculate_pagination(total=95, page=5, page_size=20)
        assert result["offset"] == 80
        assert result["total_pages"] == 5
        assert result["has_next"] is False

    def test_single_item(self):
        """Test single item"""
        result = calculate_pagination(total=1, page=1, page_size=20)
        assert result["offset"] == 0
        assert result["total_pages"] == 1
        assert result["has_next"] is False
        assert result["has_prev"] is False


class TestPaginatedResponse:
    """Test PaginatedResponse model"""

    def test_create_response(self):
        """Test creating paginated response"""
        response = PaginatedResponse(
            items=[{"id": 1}, {"id": 2}],
            total=100,
            page=1,
            page_size=20,
            total_pages=5,
        )
        assert response.total == 100
        assert len(response.items) == 2
        assert response.page == 1

    def test_empty_response(self):
        """Test empty paginated response"""
        response = PaginatedResponse(
            items=[],
            total=0,
            page=1,
            page_size=20,
            total_pages=0,
        )
        assert response.total == 0
        assert response.items == []
