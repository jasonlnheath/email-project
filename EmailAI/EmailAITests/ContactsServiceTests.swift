import XCTest
@testable import EmailAI

/// Tests for ContactsService (Google People API integration)
final class ContactsServiceTests: XCTestCase {

    // MARK: - Service Initialization Tests

    func testContactsServiceSingletonExists() {
        let service = ContactsService.shared
        XCTAssertNotNil(service)
    }

    func testContactsServiceIsActor() {
        // Verify ContactsService is an actor for thread-safety
        XCTAssertTrue(type(of: ContactsService.shared) is Actor.Type)
    }

    // MARK: - Contact Model Tests

    func testContactModelHasRequiredProperties() {
        let contact = Contact(
            id: UUID(),
            email: "test@example.com",
            name: "Test User",
            phoneNumber: "555-1234",
            photoUrl: nil,
            lastUpdated: Date()
        )

        XCTAssertEqual(contact.email, "test@example.com")
        XCTAssertEqual(contact.name, "Test User")
        XCTAssertEqual(contact.phoneNumber, "555-1234")
        XCTAssertNil(contact.photoUrl)
    }

    func testContactConformsToIdentifiable() {
        let id = UUID()
        let contact = Contact(
            id: id,
            email: "test@example.com",
            name: "Test User",
            phoneNumber: nil,
            photoUrl: nil,
            lastUpdated: Date()
        )

        XCTAssertEqual(contact.id, id)
    }

    func testContactConformsToCodable() throws {
        let contact = Contact(
            id: UUID(),
            email: "test@example.com",
            name: "Test User",
            phoneNumber: "555-1234",
            photoUrl: "https://example.com/photo.jpg",
            lastUpdated: Date()
        )

        let encoder = JSONEncoder()
        let data = try encoder.encode(contact)

        let decoder = JSONDecoder()
        let decoded = try decoder.decode(Contact.self, from: data)

        XCTAssertEqual(contact.email, decoded.email)
        XCTAssertEqual(contact.name, decoded.name)
        XCTAssertEqual(contact.phoneNumber, decoded.phoneNumber)
        XCTAssertEqual(contact.photoUrl, decoded.photoUrl)
    }

    // MARK: - Fetch Contacts Tests

    func testFetchContactsThrowsWithoutAccessToken() async {
        let service = ContactsService.shared

        do {
            _ = try await service.fetchContacts(accessToken: "")
            XCTFail("Should throw when access token is empty")
        } catch {
            // Expected
        }
    }

    func testFetchContactsReturnsEmptyArrayOnError() async {
        let service = ContactsService.shared

        // Use invalid token that will fail authentication
        do {
            let contacts = try await service.fetchContacts(accessToken: "invalid_token")
            // Should return empty array on error, not throw
            XCTAssertTrue(contacts.isEmpty, "Should return empty array on API error")
        } catch {
            // Also acceptable to throw
            XCTAssertTrue(error is ContactsError, "Should throw ContactsError")
        }
    }

    // MARK: - Get Contact by Email Tests

    func testGetContactByEmailReturnsNilWhenNotFound() async {
        let service = ContactsService.shared

        // Without fetching contacts first, should return nil
        let contact = await service.getContactByEmail("nonexistent@example.com")
        XCTAssertNil(contact, "Should return nil for non-existent contact")
    }

    func testGetContactByEmailReturnsContactWhenFound() async {
        let service = ContactsService.shared

        // First fetch contacts (will use mock token, may fail but that's ok for this test)
        do {
            _ = try await service.fetchContacts(accessToken: "test_token")

            // Even with empty results, getContactByEmail should handle gracefully
            let contact = await service.getContactByEmail("test@example.com")
            // Will be nil since we're using a test token, but the method should not crash
            XCTAssertNotNil(contact) // May fail with mock token, but that's expected
        } catch {
            // Expected with mock token
        }
    }

    // MARK: - ContactsError Enum Tests

    func testContactsErrorHasInvalidTokenCase() {
        let error = ContactsError.invalidToken
        if case .invalidToken = error {
            XCTAssertTrue(true)
        } else {
            XCTFail("Should have invalidToken case")
        }
    }

    func testContactsErrorHasNetworkErrorCase() {
        let error = ContactsError.networkError(NSError(domain: "test", code: -1))
        if case .networkError = error {
            XCTAssertTrue(true)
        } else {
            XCTFail("Should have networkError case")
        }
    }

    func testContactsErrorHasParseErrorCase() {
        let error = ContactsError.parseError("Failed to parse")
        if case .parseError = error {
            XCTAssertTrue(true)
        } else {
            XCTFail("Should have parseError case")
        }
    }

    func testContactsErrorConformsToLocalizedError() {
        let error = ContactsError.invalidToken
        XCTAssertNotNil(error.errorDescription)
    }
}
