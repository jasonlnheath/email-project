import Foundation

/// Gmail API client — fetches emails using the REST API.
actor GmailService {
    private let baseURL = "https://gmail.googleapis.com/gmail/v1/users/me"

    /// Fetch recent emails using an access token.
    func fetchEmails(accessToken: String, maxResults: Int = 50) async throws -> [GmailMessage] {
        // TEMPORARY: Fetch all recent emails for testing (not just unread)
        // This helps find school newsletters and test HTML summarization
        let urlString = "\(baseURL)/messages?maxResults=\(maxResults)&q=in:inbox+newer_than:7d"
        var request = URLRequest(url: URL(string: urlString)!)
        request.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")

        let (data, _) = try await URLSession.shared.data(for: request)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        let messages = json?["messages"] as? [[String: String]] ?? []

        var results: [GmailMessage] = []
        for msg in messages {
            if let id = msg["id"] {
                let detail = try await fetchMessageDetail(id: id, accessToken: accessToken)
                results.append(detail)
            }
        }
        return results
    }

    private func fetchMessageDetail(id: String, accessToken: String) async throws -> GmailMessage {
        let urlString = "\(baseURL)/messages/\(id)?format=full"
        var request = URLRequest(url: URL(string: urlString)!)
        request.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")

        let (data, _) = try await URLSession.shared.data(for: request)
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] ?? [:]

        let headers = (json["payload"] as? [String: Any])?["headers"] as? [[String: String]] ?? []
        let subject = headers.first { $0["name"] == "Subject" }?["value"] ?? "(no subject)"
        let from = headers.first { $0["name"] == "From" }?["value"] ?? "Unknown"
        let dateStr = headers.first { $0["name"] == "Date" }?["value"] ?? ""
        let threadId = json["threadId"] as? String ?? id
        let snippet = json["snippet"] as? String ?? ""

        // Extract labels
        let labelIds = json["labelIds"] as? [String] ?? []
        let isUnread = labelIds.contains("UNREAD")
        let isStarred = labelIds.contains("STARRED")

        // Check if deferred (has DEFERRED label)
        let isDeferred = labelIds.contains("DEFERRED")

        // Extract body
        let body = extractBody(from: json["payload"] as? [String: Any])

        // Extract unsubscribe URL
        let unsubscribeUrl = extractUnsubscribeUrl(from: body)

        return GmailMessage(
            id: id,
            threadId: threadId,
            subject: subject,
            sender: from,
            date: dateStr,
            body: body,
            snippet: snippet,
            gmailUrl: "https://mail.google.com/mail/mu/mp/330/#cv/Inbox/\(id)",
            isUnread: isUnread,
            isStarred: isStarred,
            isDeferred: isDeferred,
            unsubscribeUrl: unsubscribeUrl
        )
    }

    private func extractBody(from payload: [String: Any]?) -> String {
        print("\n📧 === extractBody() called ===")
        guard let payload else {
            print("⚠️ extractBody: payload is nil")
            return ""
        }

        var extractedBody: String?

        // Check for multipart messages
        if let parts = payload["parts"] as? [[String: Any]] {
            print("📧 Found \(parts.count) parts in email")
            for (index, part) in parts.enumerated() {
                if let mimeType = part["mimeType"] as? String {
                    print("   Part \(index): MIME type = \(mimeType)")
                }
            }

            // First priority: text/plain
            for part in parts {
                if part["mimeType"] as? String == "text/plain" {
                    if let bodyDict = part["body"] as? [String: Any],
                       let data = bodyDict["data"] as? String {
                        let decoded = decodeBase64URL(data)
                        print("✅ Found text/plain part, decoded length: \(decoded.count)")
                        if decoded.count > 0 {
                            print("   Preview: \(String(decoded.prefix(100)))")
                            extractedBody = decoded
                            break
                        }
                    }
                }
            }

            // Second priority: text/html with tag stripping
            if extractedBody == nil || extractedBody?.isEmpty == true {
                for part in parts {
                    if part["mimeType"] as? String == "text/html" {
                        if let bodyDict = part["body"] as? [String: Any],
                           let data = bodyDict["data"] as? String {
                            let html = decodeBase64URL(data)
                            let plainText = stripHTMLTags(from: html)
                            print("✅ Found text/html part, stripped to plain text, length: \(plainText.count)")
                            if plainText.count > 0 {
                                print("   Preview: \(String(plainText.prefix(100)))")
                                extractedBody = plainText
                                break
                            }
                        }
                    }
                }
            }

            // Third priority: try any part with body data
            if extractedBody == nil || extractedBody?.isEmpty == true {
                for part in parts {
                    if let bodyDict = part["body"] as? [String: Any],
                       let data = bodyDict["data"] as? String,
                       !data.isEmpty {
                        let decoded = decodeBase64URL(data)
                        if decoded.count > 0 {
                            print("⚠️ Using fallback (first part with data), MIME: \(part["mimeType"] as? String ?? "unknown"), length: \(decoded.count)")
                            print("   Preview: \(String(decoded.prefix(100)))")
                            extractedBody = decoded
                            break
                        }
                    }
                }
            }

            if extractedBody == nil || extractedBody?.isEmpty == true {
                print("❌ No parts had extractable body data")
            }
        }

        // Direct body (single part message)
        if extractedBody == nil || extractedBody?.isEmpty == true {
            if let bodyDict = payload["body"] as? [String: Any],
               let data = bodyDict["data"] as? String {
                let decoded = decodeBase64URL(data)
                print("✅ Found direct body, decoded length: \(decoded.count)")
                print("   Preview: \(String(decoded.prefix(100)))")
                extractedBody = decoded
            }
        }

        // Safety check: if body contains HTML tags, strip them (even if marked as text/plain)
        if var body = extractedBody, !body.isEmpty {
            if body.contains("<") && body.contains(">") {
                let hasHTMLTags = body.range(of: "<[^>]+>", options: .regularExpression) != nil
                if hasHTMLTags {
                    print("⚠️ Body contains HTML tags despite MIME type, stripping...")
                    let stripped = stripHTMLTags(from: body)
                    print("✅ Stripped to plain text, length: \(stripped.count)")
                    print("   Preview: \(String(stripped.prefix(100)))")
                    return stripped
                }
            }
            return body
        }

        print("❌ extractBody: No body found, returning empty string")
        return ""
    }

    /// Strip HTML tags from string (enhanced BeautifulSoup-like approach)
    private func stripHTMLTags(from html: String) -> String {
        var result = html

        // Remove script, style, nav, footer, header elements completely (like BeautifulSoup)
        result = result.replacingOccurrences(of: "<script[^>]*>.*?</script>", with: "", options: [.regularExpression, .caseInsensitive])
        result = result.replacingOccurrences(of: "<style[^>]*>.*?</style>", with: "", options: [.regularExpression, .caseInsensitive])
        result = result.replacingOccurrences(of: "<nav[^>]*>.*?</nav>", with: "", options: [.regularExpression, .caseInsensitive])
        result = result.replacingOccurrences(of: "<footer[^>]*>.*?</footer>", with: "", options: [.regularExpression, .caseInsensitive])
        result = result.replacingOccurrences(of: "<header[^>]*>.*?</header>", with: "", options: [.regularExpression, .caseInsensitive])
        result = result.replacingOccurrences(of: "<iframe[^>]*>.*?</iframe>", with: "", options: [.regularExpression, .caseInsensitive])
        result = result.replacingOccurrences(of: "<noscript[^>]*>.*?</noscript>", with: "", options: [.regularExpression, .caseInsensitive])

        // Extract alt text from images before removing them (like BeautifulSoup)
        var extractedImages: [String] = []
        let imagePattern = "<img[^>]*alt=[\"']([^\"']+)[\"'][^>]*>"
        if let imageRegex = try? NSRegularExpression(pattern: imagePattern, options: .caseInsensitive) {
            let range = NSRange(result.startIndex..., in: result)
            let matches = imageRegex.matches(in: result, range: range)
            for match in matches {
                if let altRange = Range(match.range(at: 1), in: result) {
                    let altText = String(result[altRange])
                    extractedImages.append("[Image: \(altText)]")
                }
            }
        }

        // Remove all remaining HTML tags
        result = result.replacingOccurrences(of: "<[^>]+>", with: "", options: .regularExpression)

        // Decode HTML entities (comprehensive list)
        result = result.replacingOccurrences(of: "&amp;", with: "&")
            .replacingOccurrences(of: "&lt;", with: "<")
            .replacingOccurrences(of: "&gt;", with: ">")
            .replacingOccurrences(of: "&quot;", with: "\"")
            .replacingOccurrences(of: "&apos;", with: "'")
            .replacingOccurrences(of: "&nbsp;", with: " ")
            .replacingOccurrences(of: "&#39;", with: "'")
            .replacingOccurrences(of: "&mdash;", with: "—")
            .replacingOccurrences(of: "&ndash;", with: "–")
            .replacingOccurrences(of: "&rsquo;", with: "'")
            .replacingOccurrences(of: "&lsquo;", with: "'")
            .replacingOccurrences(of: "&rdquo;", with: "\"")
            .replacingOccurrences(of: "&ldquo;", with: "\"")

        // Convert block elements to newlines
        result = result.replacingOccurrences(of: "</p>", with: "\n\n", options: .regularExpression)
        result = result.replacingOccurrences(of: "</div>", with: "\n", options: .regularExpression)
        result = result.replacingOccurrences(of: "<br>", with: "\n", options: [.regularExpression, .caseInsensitive])
        result = result.replacingOccurrences(of: "<br/>", with: "\n", options: [.regularExpression, .caseInsensitive])
        result = result.replacingOccurrences(of: "<br />", with: "\n", options: [.regularExpression, .caseInsensitive])
        result = result.replacingOccurrences(of: "</li>", with: "\n", options: .regularExpression)
        result = result.replacingOccurrences(of: "</td>", with: " | ", options: .regularExpression)
        result = result.replacingOccurrences(of: "</tr>", with: "\n", options: .regularExpression)

        // Prepend extracted image descriptions
        if !extractedImages.isEmpty {
            result = extractedImages.joined(separator: "\n") + "\n\n" + result
        }

        // Clean up excessive whitespace and blank lines
        result = result.replacingOccurrences(of: "\\s+", with: " ", options: .regularExpression)
        result = result.replacingOccurrences(of: "\\n\\s*\\n\\s*\\n+", with: "\n\n", options: .regularExpression)
        result = result.trimmingCharacters(in: .whitespacesAndNewlines)

        return result
    }

    /// Extract unsubscribe URL from email body
    private func extractUnsubscribeUrl(from body: String) -> String? {
        // Look for common unsubscribe patterns
        let patterns = [
            "<(.+unsubscribe.+)>",
            "https?://[^\\s<>]+unsubscribe[^\\s<>]*",
            "<a[^>]*href=['\\\"]([^'\\\"]*unsubscribe[^'\\\"]*)['\\\"]",
        ]

        for pattern in patterns {
            if let regex = try? NSRegularExpression(pattern: pattern, options: .caseInsensitive),
               let match = regex.firstMatch(in: body, range: NSRange(body.startIndex..., in: body)) {
                let matchRange = Range(match.range, in: body)
                if let range = matchRange {
                    var url = String(body[range])
                    // Clean up the URL by removing quotes, angle brackets
                    let charsToRemove = CharacterSet(charactersIn: "<>\"'")
                    url = url.components(separatedBy: charsToRemove).joined(separator: "")
                    if url.hasPrefix("http") {
                        return url
                    }
                }
            }
        }

        return nil
    }

    private func decodeBase64URL(_ str: String) -> String {
        // URL-safe base64 decode (matching Python's base64.urlsafe_b64decode)
        let padded = str
            .replacingOccurrences(of: "-", with: "+")
            .replacingOccurrences(of: "_", with: "/")

        // Calculate required padding (base64 strings must be multiple of 4)
        let paddingLength = (4 - padded.count % 4) % 4
        let padding = String(repeating: "=", count: paddingLength)

        guard let data = Data(base64Encoded: padded + padding) else {
            print("⚠️ Base64 decoding failed for string starting with: \(String(str.prefix(20)))")
            return ""
        }

        guard let decoded = String(data: data, encoding: .utf8) else {
            print("⚠️ UTF-8 decoding failed for base64 data")
            return ""
        }

        return decoded
    }
}

/// Errors that can occur during Gmail actions
enum GmailActionsError: Error, LocalizedError {
    case invalidAccessToken
    case invalidEmailId
    case invalidUnsubscribeUrl
    case apiError(statusCode: Int)

    var errorDescription: String? {
        switch self {
        case .invalidAccessToken:
            return "Invalid access token"
        case .invalidEmailId:
            return "Invalid email ID"
        case .invalidUnsubscribeUrl:
            return "Invalid unsubscribe URL"
        case .apiError(let statusCode):
            return "API error with status code: \(statusCode)"
        }
    }
}

/// Gmail API actions service - performs actions on emails (mark read, delete, defer, star, unsubscribe)
actor GmailActionsService {
    private let baseURL = "https://gmail.googleapis.com/gmail/v1/users/me"

    /// Mark an email as read or unread
    func markAsRead(emailId: String, accessToken: String) async throws {
        guard !accessToken.isEmpty else {
            throw GmailActionsError.invalidAccessToken
        }
        guard !emailId.isEmpty else {
            throw GmailActionsError.invalidEmailId
        }

        // Remove UNREAD label to mark as read
        let urlString = "\(baseURL)/messages/\(emailId)/modify"
        var request = URLRequest(url: URL(string: urlString)!)
        request.httpMethod = "POST"
        request.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let body: [String: Any] = [
            "removeLabelIds": ["UNREAD"]
        ]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (_, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              (200...299).contains(httpResponse.statusCode) else {
            throw GmailActionsError.apiError(statusCode: (response as? HTTPURLResponse)?.statusCode ?? 0)
        }
    }

    /// Mark an email as unread
    func markAsUnread(emailId: String, accessToken: String) async throws {
        guard !accessToken.isEmpty else {
            throw GmailActionsError.invalidAccessToken
        }
        guard !emailId.isEmpty else {
            throw GmailActionsError.invalidEmailId
        }

        // Add UNREAD label to mark as unread
        let urlString = "\(baseURL)/messages/\(emailId)/modify"
        var request = URLRequest(url: URL(string: urlString)!)
        request.httpMethod = "POST"
        request.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let body: [String: Any] = [
            "addLabelIds": ["UNREAD"]
        ]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (_, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              (200...299).contains(httpResponse.statusCode) else {
            throw GmailActionsError.apiError(statusCode: (response as? HTTPURLResponse)?.statusCode ?? 0)
        }
    }

    /// Delete an email (move to trash)
    func deleteEmail(emailId: String, accessToken: String) async throws {
        guard !accessToken.isEmpty else {
            throw GmailActionsError.invalidAccessToken
        }
        guard !emailId.isEmpty else {
            throw GmailActionsError.invalidEmailId
        }

        let urlString = "\(baseURL)/messages/\(emailId)/trash"
        var request = URLRequest(url: URL(string: urlString)!)
        request.httpMethod = "POST"
        request.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")

        let (_, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              (200...299).contains(httpResponse.statusCode) else {
            throw GmailActionsError.apiError(statusCode: (response as? HTTPURLResponse)?.statusCode ?? 0)
        }
    }

    /// Defer an email by adding a "DEFERRED" label
    func deferEmail(emailId: String, accessToken: String) async throws {
        guard !accessToken.isEmpty else {
            throw GmailActionsError.invalidAccessToken
        }
        guard !emailId.isEmpty else {
            throw GmailActionsError.invalidEmailId
        }

        // Try to find or create the DEFERRED label
        let labelId = await getOrCreateDeferredLabel(accessToken: accessToken)

        guard let labelId = labelId else {
            // If we can't create/get the label, just mark as read and archive
            try await markAsRead(emailId: emailId, accessToken: accessToken)
            try await archiveEmail(emailId: emailId, accessToken: accessToken)
            return
        }

        let urlString = "\(baseURL)/messages/\(emailId)/modify"
        var request = URLRequest(url: URL(string: urlString)!)
        request.httpMethod = "POST"
        request.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let body: [String: Any] = [
            "addLabelIds": [labelId],
            "removeLabelIds": ["INBOX"]
        ]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (_, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              (200...299).contains(httpResponse.statusCode) else {
            throw GmailActionsError.apiError(statusCode: (response as? HTTPURLResponse)?.statusCode ?? 0)
        }
    }

    /// Get or create the DEFERRED label, returns its ID or nil
    private func getOrCreateDeferredLabel(accessToken: String) async -> String? {
        // First, try to get existing labels
        let existingLabelId = await getLabelId("DEFERRED", accessToken: accessToken)
        if existingLabelId != nil {
            return existingLabelId
        }

        // Label doesn't exist, try to create it
        return await createDeferredLabel(accessToken: accessToken)
    }

    /// Create the DEFERRED label and return its ID
    private func createDeferredLabel(accessToken: String) async -> String? {
        let urlString = "\(baseURL)/labels"
        var request = URLRequest(url: URL(string: urlString)!)
        request.httpMethod = "POST"
        request.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let body: [String: Any] = [
            "name": "DEFERRED",
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
            "type": "user"
        ]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)

        do {
            let (data, response) = try await URLSession.shared.data(for: request)

            if let httpResponse = response as? HTTPURLResponse {
                // 409 means label already exists
                if httpResponse.statusCode == 409 {
                    return await getLabelId("DEFERRED", accessToken: accessToken)
                }
                // Success - return the new label ID
                if (200...299).contains(httpResponse.statusCode),
                   let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                   let labelId = json["id"] as? String {
                    return labelId
                }
            }
        } catch {
            print("Failed to create DEFERRED label: \(error)")
        }

        return nil
    }

    /// Get the label ID for a given label name
    private func getLabelId(_ labelName: String, accessToken: String) async -> String? {
        let urlString = "\(baseURL)/labels"
        var request = URLRequest(url: URL(string: urlString)!)
        request.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")

        do {
            let (data, _) = try await URLSession.shared.data(for: request)
            guard let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
                  let labels = json["labels"] as? [[String: Any]] else {
                return nil
            }

            return labels.first { label in
                (label["name"] as? String) == labelName
            }?["id"] as? String
        } catch {
            return nil
        }
    }

    /// Toggle star status on an email
    func toggleStar(emailId: String, isStarred: Bool, accessToken: String) async throws {
        guard !accessToken.isEmpty else {
            throw GmailActionsError.invalidAccessToken
        }
        guard !emailId.isEmpty else {
            throw GmailActionsError.invalidEmailId
        }

        let urlString = "\(baseURL)/messages/\(emailId)/modify"
        var request = URLRequest(url: URL(string: urlString)!)
        request.httpMethod = "POST"
        request.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let body: [String: Any]
        if isStarred {
            body = ["addLabelIds": ["STARRED"]]
        } else {
            body = ["removeLabelIds": ["STARRED"]]
        }
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (_, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              (200...299).contains(httpResponse.statusCode) else {
            throw GmailActionsError.apiError(statusCode: (response as? HTTPURLResponse)?.statusCode ?? 0)
        }
    }

    /// Unsubscribe from a mailing list using the unsubscribe URL
    func unsubscribe(emailId: String, unsubscribeUrl: String, accessToken: String) async throws {
        guard !accessToken.isEmpty else {
            throw GmailActionsError.invalidAccessToken
        }
        guard !emailId.isEmpty else {
            throw GmailActionsError.invalidEmailId
        }
        guard !unsubscribeUrl.isEmpty else {
            throw GmailActionsError.invalidUnsubscribeUrl
        }

        guard let url = URL(string: unsubscribeUrl) else {
            throw GmailActionsError.invalidUnsubscribeUrl
        }

        var request = URLRequest(url: url)
        request.httpMethod = "GET" // Most unsubscribe links use GET

        let (_, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              (200...299).contains(httpResponse.statusCode) else {
            // Unsubscribe failed, but that's okay - mark email as read and archive it
            try? await markAsRead(emailId: emailId, accessToken: accessToken)
            try? await archiveEmail(emailId: emailId, accessToken: accessToken)
            return
        }
    }

    /// Archive an email (remove INBOX label)
    private func archiveEmail(emailId: String, accessToken: String) async throws {
        let urlString = "\(baseURL)/messages/\(emailId)/modify"
        var request = URLRequest(url: URL(string: urlString)!)
        request.httpMethod = "POST"
        request.setValue("Bearer \(accessToken)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")

        let body: [String: Any] = [
            "removeLabelIds": ["INBOX"]
        ]
        request.httpBody = try JSONSerialization.data(withJSONObject: body)

        let (_, response) = try await URLSession.shared.data(for: request)

        guard let httpResponse = response as? HTTPURLResponse,
              (200...299).contains(httpResponse.statusCode) else {
            throw GmailActionsError.apiError(statusCode: (response as? HTTPURLResponse)?.statusCode ?? 0)
        }
    }

    /// Mark multiple emails as read
    func markMultipleAsRead(emailIds: [String], accessToken: String) async throws {
        guard !accessToken.isEmpty else {
            throw GmailActionsError.invalidAccessToken
        }
        guard !emailIds.isEmpty else {
            throw GmailActionsError.invalidEmailId
        }

        for emailId in emailIds {
            try? await markAsRead(emailId: emailId, accessToken: accessToken)
        }
    }

    /// Delete multiple emails
    func deleteMultiple(emailIds: [String], accessToken: String) async throws {
        guard !accessToken.isEmpty else {
            throw GmailActionsError.invalidAccessToken
        }
        guard !emailIds.isEmpty else {
            throw GmailActionsError.invalidEmailId
        }

        for emailId in emailIds {
            try? await deleteEmail(emailId: emailId, accessToken: accessToken)
        }
    }
}

struct GmailMessage: Codable {
    let id: String
    let threadId: String
    let subject: String
    let sender: String
    let date: String
    let body: String
    let snippet: String
    let gmailUrl: String
    let isUnread: Bool
    let isStarred: Bool
    let isDeferred: Bool
    let unsubscribeUrl: String?
}
