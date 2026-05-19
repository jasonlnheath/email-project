import Foundation

/// OAuth token manager for Google Sign-In
actor OAuthService {
    static let shared = OAuthService()

    private let tokenRefreshThreshold: TimeInterval = 300 // 5 minutes

    private init() {}

    // MARK: - Sign-In State

    /// Whether the user is currently signed in
    var isSignedIn: Bool {
        guard let token = KeychainService.shared.load(key: Constants.keychainGmailAccessToken) else {
            return false
        }
        return !token.isEmpty
    }

    /// The currently signed-in user's email address
    var currentUserEmail: String? {
        KeychainService.shared.load(key: Constants.keychainGmailUserEmail)
    }

    // MARK: - Token Management

    /// Get the current access token, refreshing if necessary
    func getCurrentAccessToken() async throws -> String {
        guard let token = KeychainService.shared.load(key: Constants.keychainGmailAccessToken) else {
            throw LLMError.missingAPIKey
        }

        // Check if token needs refresh
        if needsRefresh() {
            try await refreshTokens()
            // Get the new token after refresh
            guard let newToken = KeychainService.shared.load(key: Constants.keychainGmailAccessToken) else {
                throw LLMError.missingAPIKey
            }
            return newToken
        }

        return token
    }

    /// Store OAuth tokens after successful sign-in
    func storeTokens(accessToken: String, refreshToken: String, expirationDate: Date, userEmail: String) throws {
        try KeychainService.shared.save(key: Constants.keychainGmailAccessToken, value: accessToken)
        try KeychainService.shared.save(key: Constants.keychainGmailRefreshToken, value: refreshToken)
        try KeychainService.shared.save(key: Constants.keychainGmailTokenExpiry, value: ISO8601DateFormatter().string(from: expirationDate))
        try KeychainService.shared.save(key: Constants.keychainGmailUserEmail, value: userEmail)

        // Update UserDefaults to trigger UI update
        UserDefaults.standard.set(true, forKey: "isSignedIn")
    }

    /// Refresh OAuth tokens using the refresh token
    func refreshTokens() async throws {
        guard let _ = KeychainService.shared.load(key: Constants.keychainGmailRefreshToken) else {
            throw LLMError.missingAPIKey
        }

        // TODO: Implement actual token refresh via Google OAuth endpoint
        // For now, this will fail without real Google Sign-In integration
        // This is a placeholder that will be implemented when Google Sign-In SDK is added

        throw LLMError.apiError(statusCode: 501, body: "Token refresh not yet implemented - requires Google Sign-In SDK")
    }

    /// Sign out and clear all tokens
    func signOut() async throws {
        KeychainService.shared.delete(key: Constants.keychainGmailAccessToken)
        KeychainService.shared.delete(key: Constants.keychainGmailRefreshToken)
        KeychainService.shared.delete(key: Constants.keychainGmailTokenExpiry)
        KeychainService.shared.delete(key: Constants.keychainGmailUserEmail)

        // Update UserDefaults to trigger UI update
        UserDefaults.standard.set(false, forKey: "isSignedIn")
    }

    // MARK: - Private Helpers

    private func needsRefresh() -> Bool {
        guard let expiryString = KeychainService.shared.load(key: Constants.keychainGmailTokenExpiry),
              let expiryDate = ISO8601DateFormatter().date(from: expiryString) else {
            return true // No expiry date, assume needs refresh
        }

        let threshold = Date().addingTimeInterval(tokenRefreshThreshold)
        return expiryDate < threshold
    }
}

// MARK: - Additional Constants

extension Constants {
    static let keychainGmailUserEmail = "com.emailai.gmail-user-email"
}
