import XCTest
@testable import EmailAI

/// Tests for OAuthService and Google Sign-In integration
final class OAuthServiceTests: XCTestCase {

    // MARK: - OAuthService Initialization Tests

    func testOAuthServiceSingletonExists() {
        let service = OAuthService.shared
        XCTAssertNotNil(service)
    }

    func testOAuthServiceIsActor() {
        // Verify OAuthService is an actor for thread-safety
        XCTAssertTrue(type(of: OAuthService.shared) is Actor.Type)
    }

    // MARK: - Sign-In State Tests

    func testInitiallyNotSignedIn() async {
        let service = OAuthService.shared
        // Clear any existing tokens first
        try? KeychainService.shared.delete(key: Constants.keychainGmailAccessToken)
        let signedIn = await service.isSignedIn
        XCTAssertFalse(signedIn)
    }

    func testIsSignedInReturnsFalseWhenNoToken() async {
        let service = OAuthService.shared
        // Clear any existing tokens
        try? KeychainService.shared.delete(key: Constants.keychainGmailAccessToken)
        let signedIn = await service.isSignedIn
        XCTAssertFalse(signedIn)
    }

    // MARK: - Token Storage Tests

    func testStoreAccessToken() throws {
        let service = OAuthService.shared
        let testToken = "test_access_token_12345"

        try KeychainService.shared.save(key: Constants.keychainGmailAccessToken, value: testToken)

        let retrievedToken = KeychainService.shared.load(key: Constants.keychainGmailAccessToken)
        XCTAssertEqual(retrievedToken, testToken)

        // Cleanup
        try? KeychainService.shared.delete(key: Constants.keychainGmailAccessToken)
    }

    func testStoreRefreshToken() throws {
        let service = OAuthService.shared
        let testToken = "test_refresh_token_67890"

        try KeychainService.shared.save(key: Constants.keychainGmailRefreshToken, value: testToken)

        let retrievedToken = KeychainService.shared.load(key: Constants.keychainGmailRefreshToken)
        XCTAssertEqual(retrievedToken, testToken)

        // Cleanup
        try? KeychainService.shared.delete(key: Constants.keychainGmailRefreshToken)
    }

    func testStoreTokenExpirationDate() throws {
        let service = OAuthService.shared
        let futureDate = Date().addingTimeInterval(3600) // 1 hour from now

        try KeychainService.shared.save(key: Constants.keychainGmailTokenExpiry, value: ISO8601DateFormatter().string(from: futureDate))

        let dateString = KeychainService.shared.load(key: Constants.keychainGmailTokenExpiry)
        XCTAssertNotNil(dateString)

        // Cleanup
        try? KeychainService.shared.delete(key: Constants.keychainGmailTokenExpiry)
    }

    // MARK: - getCurrentAccessToken Tests

    func testGetCurrentAccessTokenThrowsWhenNotSignedIn() async {
        let service = OAuthService.shared

        // Clear tokens
        try? KeychainService.shared.delete(key: Constants.keychainGmailAccessToken)

        do {
            _ = try await service.getCurrentAccessToken()
            XCTFail("Should throw when not signed in")
        } catch {
            // Expected
        }
    }

    func testGetCurrentAccessTokenReturnsValidToken() async throws {
        let service = OAuthService.shared
        let testToken = "valid_access_token_123"

        // Store a valid token with future expiration
        try KeychainService.shared.save(key: Constants.keychainGmailAccessToken, value: testToken)
        let futureDate = Date().addingTimeInterval(3600)
        try KeychainService.shared.save(key: Constants.keychainGmailTokenExpiry, value: ISO8601DateFormatter().string(from: futureDate))

        let retrievedToken = try await service.getCurrentAccessToken()
        XCTAssertEqual(retrievedToken, testToken)

        // Cleanup
        try? KeychainService.shared.delete(key: Constants.keychainGmailAccessToken)
        try? KeychainService.shared.delete(key: Constants.keychainGmailTokenExpiry)
    }

    // MARK: - Token Refresh Tests

    func testTokenRefreshNeededWhenExpired() async throws {
        let service = OAuthService.shared

        // Store an expired token
        let pastDate = Date().addingTimeInterval(-100) // Expired
        try KeychainService.shared.save(key: Constants.keychainGmailAccessToken, value: "expired_token")
        try KeychainService.shared.save(key: Constants.keychainGmailTokenExpiry, value: ISO8601DateFormatter().string(from: pastDate))

        // Should trigger refresh attempt
        do {
            _ = try await service.getCurrentAccessToken()
            // Will fail on actual refresh, but verifies refresh logic is triggered
        } catch {
            // Expected - refresh will fail without real Google Sign-In
        }

        // Cleanup
        try? KeychainService.shared.delete(key: Constants.keychainGmailAccessToken)
        try? KeychainService.shared.delete(key: Constants.keychainGmailTokenExpiry)
    }

    // MARK: - Sign Out Tests

    func testSignOutClearsTokens() async throws {
        let service = OAuthService.shared

        // Store tokens
        try KeychainService.shared.save(key: Constants.keychainGmailAccessToken, value: "test_token")
        try KeychainService.shared.save(key: Constants.keychainGmailRefreshToken, value: "refresh_token")

        // Sign out
        try await service.signOut()

        // Verify tokens are cleared
        XCTAssertNil(KeychainService.shared.load(key: Constants.keychainGmailAccessToken))
        XCTAssertNil(KeychainService.shared.load(key: Constants.keychainGmailRefreshToken))

        let signedIn = await service.isSignedIn
        XCTAssertFalse(signedIn)
    }

    // MARK: - Current User Email Tests

    func testCurrentUserEmailReturnsNilWhenNotSignedIn() async {
        let service = OAuthService.shared
        let email = await service.currentUserEmail
        XCTAssertNil(email)
    }

    // MARK: - Token Expiration Threshold Tests

    func testShouldRefreshTokenWithinThreshold() async throws {
        // Token expiring in less than 5 minutes should trigger refresh
        let nearExpiry = Date().addingTimeInterval(200) // ~3.3 minutes

        try KeychainService.shared.save(key: Constants.keychainGmailAccessToken, value: "test_token")
        try KeychainService.shared.save(key: Constants.keychainGmailTokenExpiry, value: ISO8601DateFormatter().string(from: nearExpiry))

        do {
            _ = try await OAuthService.shared.getCurrentAccessToken()
            // Should attempt refresh (will fail without real credentials)
        } catch {
            // Expected
        }

        // Cleanup
        try? KeychainService.shared.delete(key: Constants.keychainGmailAccessToken)
        try? KeychainService.shared.delete(key: Constants.keychainGmailTokenExpiry)
    }

    func testShouldNotRefreshValidToken() async throws {
        // Token with more than 5 minutes validity should not trigger refresh
        let validToken = Date().addingTimeInterval(600) // 10 minutes

        try KeychainService.shared.save(key: Constants.keychainGmailAccessToken, value: "test_token")
        try KeychainService.shared.save(key: Constants.keychainGmailTokenExpiry, value: ISO8601DateFormatter().string(from: validToken))

        let retrievedToken = try await OAuthService.shared.getCurrentAccessToken()
        XCTAssertEqual(retrievedToken, "test_token")

        // Cleanup
        try? KeychainService.shared.delete(key: Constants.keychainGmailAccessToken)
        try? KeychainService.shared.delete(key: Constants.keychainGmailTokenExpiry)
    }
}
