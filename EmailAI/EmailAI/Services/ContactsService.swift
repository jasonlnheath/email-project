import Foundation

/// Service for fetching and managing contacts from Google People API
actor ContactsService {
    static let shared = ContactsService()

    private var cachedContacts: [Contact] = []

    private init() {}

    // MARK: - Fetch Contacts

    /// Fetch contacts from Google People API
    /// - Parameter accessToken: Valid OAuth access token
    /// - Returns: Array of Contact objects
    func fetchContacts(accessToken: String) async throws -> [Contact] {
        guard !accessToken.isEmpty else {
            throw ContactsError.invalidToken
        }

        // Google People API endpoint
        let urlString = "https://people.googleapis.com/v1/people/me/connections?personFields=names,emailAddresses,photos,phoneNumbers"

        guard let url = URL(string: urlString) else {
            throw ContactsError.parseError("Invalid URL")
        }

        var request = URLRequest(url: url)
        request.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")

        do {
            let (data, response) = try await URLSession.shared.data(for: request)

            guard let httpResponse = response as? HTTPURLResponse else {
                throw ContactsError.parseError("Invalid response")
            }

            if httpResponse.statusCode != 200 {
                if httpResponse.statusCode == 401 {
                    throw ContactsError.invalidToken
                }
                throw ContactsError.networkError(NSError(domain: "ContactsService", code: httpResponse.statusCode))
            }

            // Parse response
            let contacts = try parseContactsResponse(data: data)
            cachedContacts = contacts
            return contacts

        } catch let error as ContactsError {
            throw error
        } catch {
            throw ContactsError.networkError(error)
        }
    }

    // MARK: - Get Contact by Email

    /// Get a contact by email address
    /// - Parameter email: Email address to search for
    /// - Returns: Contact if found, nil otherwise
    func getContactByEmail(_ email: String) -> Contact? {
        return cachedContacts.first { $0.email == email }
    }

    // MARK: - Private Helpers

    private func parseContactsResponse(data: Data) throws -> [Contact] {
        do {
            let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            guard let connections = json?["connections"] as? [[String: Any]] else {
                return []
            }

            var contacts: [Contact] = []

            for person in connections {
                // Extract email
                var email: String?
                if let emailAddresses = person["emailAddresses"] as? [[String: Any]],
                   let firstEmail = emailAddresses.first,
                   let emailValue = firstEmail["value"] as? String {
                    email = emailValue
                }

                // Only create contact if we have an email
                guard let contactEmail = email else {
                    continue
                }

                // Extract name
                var name: String?
                if let names = person["names"] as? [[String: Any]],
                   let firstName = names.first,
                   let displayName = firstName["displayName"] as? String {
                    name = displayName
                }

                // Extract phone number
                var phoneNumber: String?
                if let phoneNumbers = person["phoneNumbers"] as? [[String: Any]],
                   let firstPhone = phoneNumbers.first,
                   let phoneValue = firstPhone["value"] as? String {
                    phoneNumber = phoneValue
                }

                // Extract photo URL
                var photoUrl: String?
                if let photos = person["photos"] as? [[String: Any]],
                   let firstPhoto = photos.first,
                   let photoUrlValue = firstPhoto["url"] as? String {
                    photoUrl = photoUrlValue
                }

                let contact = Contact(
                    email: contactEmail,
                    name: name,
                    phoneNumber: phoneNumber,
                    photoUrl: photoUrl,
                    lastUpdated: Date()
                )

                contacts.append(contact)
            }

            return contacts

        } catch {
            throw ContactsError.parseError("Failed to parse JSON: \(error.localizedDescription)")
        }
    }
}
