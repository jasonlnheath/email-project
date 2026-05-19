import XCTest
@testable import EmailAI

/// Tests for GmailActionsService (Gmail API email actions)
final class GmailActionsServiceTests: XCTestCase {

    // MARK: - Service Initialization Tests

    func testGmailActionsServiceExists() {
        let service = GmailActionsService()
        XCTAssertNotNil(service)
    }

    func testGmailActionsServiceIsActor() {
        // Verify GmailActionsService is an actor for thread-safety
        XCTAssertTrue(type(of: GmailActionsService()) is Actor.Type)
    }

    // MARK: - Mark as Read Tests

    func testMarkAsReadThrowsWithoutAccessToken() async {
        let service = GmailActionsService()

        do {
            try await service.markAsRead(emailId: "test_id", accessToken: "")
            XCTFail("Should throw when access token is empty")
        } catch {
            // Expected
        }
    }

    func testMarkAsReadThrowsWithoutEmailId() async {
        let service = GmailActionsService()

        do {
            try await service.markAsRead(emailId: "", accessToken: "valid_token")
            XCTFail("Should throw when emailId is empty")
        } catch {
            // Expected
        }
    }

    // MARK: - Delete Email Tests

    func testDeleteEmailThrowsWithoutAccessToken() async {
        let service = GmailActionsService()

        do {
            try await service.deleteEmail(emailId: "test_id", accessToken: "")
            XCTFail("Should throw when access token is empty")
        } catch {
            // Expected
        }
    }

    func testDeleteEmailThrowsWithoutEmailId() async {
        let service = GmailActionsService()

        do {
            try await service.deleteEmail(emailId: "", accessToken: "valid_token")
            XCTFail("Should throw when emailId is empty")
        } catch {
            // Expected
        }
    }

    // MARK: - Defer Email Tests

    func testDeferEmailThrowsWithoutAccessToken() async {
        let service = GmailActionsService()

        do {
            try await service.deferEmail(emailId: "test_id", accessToken: "")
            XCTFail("Should throw when access token is empty")
        } catch {
            // Expected
        }
    }

    func testDeferEmailThrowsWithoutEmailId() async {
        let service = GmailActionsService()

        do {
            try await service.deferEmail(emailId: "", accessToken: "valid_token")
            XCTFail("Should throw when emailId is empty")
        } catch {
            // Expected
        }
    }

    // MARK: - Toggle Star Tests

    func testToggleStarThrowsWithoutAccessToken() async {
        let service = GmailActionsService()

        do {
            try await service.toggleStar(emailId: "test_id", isStarred: true, accessToken: "")
            XCTFail("Should throw when access token is empty")
        } catch {
            // Expected
        }
    }

    func testToggleStarThrowsWithoutEmailId() async {
        let service = GmailActionsService()

        do {
            try await service.toggleStar(emailId: "", isStarred: true, accessToken: "valid_token")
            XCTFail("Should throw when emailId is empty")
        } catch {
            // Expected
        }
    }

    // MARK: - Unsubscribe Tests

    func testUnsubscribeThrowsWithoutAccessToken() async {
        let service = GmailActionsService()

        do {
            try await service.unsubscribe(emailId: "test_id", unsubscribeUrl: "https://example.com/unsubscribe", accessToken: "")
            XCTFail("Should throw when access token is empty")
        } catch {
            // Expected
        }
    }

    func testUnsubscribeThrowsWithoutEmailId() async {
        let service = GmailActionsService()

        do {
            try await service.unsubscribe(emailId: "", unsubscribeUrl: "https://example.com/unsubscribe", accessToken: "valid_token")
            XCTFail("Should throw when emailId is empty")
        } catch {
            // Expected
        }
    }

    func testUnsubscribeThrowsWithoutUnsubscribeUrl() async {
        let service = GmailActionsService()

        do {
            try await service.unsubscribe(emailId: "test_id", unsubscribeUrl: "", accessToken: "valid_token")
            XCTFail("Should throw when unsubscribeUrl is empty")
        } catch {
            // Expected
        }
    }

    // MARK: - Batch Actions Tests

    func testMarkMultipleAsReadThrowsWithoutAccessToken() async {
        let service = GmailActionsService()

        do {
            try await service.markMultipleAsRead(emailIds: ["id1", "id2"], accessToken: "")
            XCTFail("Should throw when access token is empty")
        } catch {
            // Expected
        }
    }

    func testMarkMultipleAsReadThrowsWithEmptyArray() async {
        let service = GmailActionsService()

        do {
            try await service.markMultipleAsRead(emailIds: [], accessToken: "valid_token")
            XCTFail("Should throw when emailIds array is empty")
        } catch {
            // Expected
        }
    }

    func testDeleteMultipleThrowsWithoutAccessToken() async {
        let service = GmailActionsService()

        do {
            try await service.deleteMultiple(emailIds: ["id1", "id2"], accessToken: "")
            XCTFail("Should throw when access token is empty")
        } catch {
            // Expected
        }
    }

    func testDeleteMultipleThrowsWithEmptyArray() async {
        let service = GmailActionsService()

        do {
            try await service.deleteMultiple(emailIds: [], accessToken: "valid_token")
            XCTFail("Should throw when emailIds array is empty")
        } catch {
            // Expected
        }
    }
}
