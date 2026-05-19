import SwiftUI

@MainActor
class EmailListViewModel: ObservableObject {
    @Published var emails: [EmailItem] = []
    @Published var summaries: [SummaryItem] = []
    @Published var isFetching = false
    @Published var errorMessage: String?
    @Published var isSignedIn = false
    @Published var vipContacts: [Contact] = []

    private let gmailService = GmailService()
    private let contactsService = ContactsService.shared
    private let gmailActionsService = GmailActionsService()

    init() {
        Task {
            isSignedIn = await OAuthService.shared.isSignedIn
        }
    }

    func fetchEmails() {
        isFetching = true
        errorMessage = nil

        Task { [weak self] in
            guard let self = self else { return }

            do {
                // Get OAuth token
                let accessToken = try await OAuthService.shared.getCurrentAccessToken()

                // Fetch VIP contacts for priority calculation
                let contacts = try await self.contactsService.fetchContacts(accessToken: accessToken)
                self.vipContacts = contacts

                // Fetch emails from Gmail
                let gmailMessages = try await self.gmailService.fetchEmails(accessToken: accessToken)

                // Convert to EmailItem models with new fields
                let dateFormatter = ISO8601DateFormatter()
                let items = gmailMessages.map { message -> EmailItem in
                    let emailItem = EmailItem(
                        emailId: message.id,
                        subject: message.subject,
                        sender: message.sender,
                        date: dateFormatter.date(from: message.date) ?? Date(),
                        body: message.body,
                        snippet: message.snippet,
                        gmailUrl: message.gmailUrl,
                        isRead: !message.isUnread,
                        isStarred: message.isStarred,
                        isDeferred: message.isDeferred,
                        priority: .medium,  // Will be calculated below
                        unsubscribeUrl: message.unsubscribeUrl
                    )

                    // Calculate priority based on VIP contacts and content
                    let priority = EmailPriorityCalculator.calculate(for: emailItem, vipContacts: contacts)
                    var updatedItem = emailItem
                    updatedItem.priority = priority

                    // Set VIP info if applicable
                    if let vip = contacts.first(where: { emailItem.sender.contains($0.email) }) {
                        updatedItem.vipInfo = VIPInfo(name: vip.name ?? "Unknown", relationshipType: "VIP")
                    }

                    return updatedItem
                }

                await MainActor.run {
                    self.emails = items
                    self.isFetching = false
                    self.isSignedIn = true
                }
            } catch {
                await MainActor.run {
                    self.isFetching = false

                    // If error is about missing API key, user needs to sign in
                    if case LLMError.missingAPIKey = error {
                        self.errorMessage = "Please sign in with Google to fetch emails"
                    } else {
                        self.errorMessage = error.localizedDescription
                    }
                }
            }
        }
    }

    func loadSampleData() {
        emails = (0..<20).map { i in
            EmailItem(
                emailId: "sample_\(i)",
                subject: "Sample Email \(i + 1)",
                sender: "sender\(i)@example.com",
                date: Date().addingTimeInterval(Double(-i * 3600)),
                body: "This is the body of sample email \(i + 1). It contains some content about various topics like budgets, meetings, and project updates.",
                snippet: "This is the body of sample email \(i + 1)..."
            )
        }
    }

    func signOut() {
        Task {
            do {
                try await OAuthService.shared.signOut()
                await MainActor.run {
                    self.emails = []
                    self.summaries = []
                    self.isSignedIn = false
                }
            } catch {
                await MainActor.run {
                    self.errorMessage = error.localizedDescription
                }
            }
        }
    }

    // MARK: - Email Actions

    func toggleRead(for email: EmailItem) {
        Task {
            do {
                let accessToken = try await OAuthService.shared.getCurrentAccessToken()
                let newReadState = !email.isRead
                if newReadState {
                    try await gmailActionsService.markAsRead(emailId: email.emailId, accessToken: accessToken)
                } else {
                    try await gmailActionsService.markAsUnread(emailId: email.emailId, accessToken: accessToken)
                }

                await MainActor.run {
                    self.emails = self.emails.map { email in
                        if email.emailId == email.emailId {
                            var updated = email
                            updated.isRead = newReadState
                            return updated
                        }
                        return email
                    }
                }
            } catch {
                await MainActor.run {
                    self.errorMessage = "Failed to update read status: \(error.localizedDescription)"
                }
            }
        }
    }

    func toggleStar(for email: EmailItem) {
        Task {
            do {
                let accessToken = try await OAuthService.shared.getCurrentAccessToken()
                let newStarState = !email.isStarred
                try await gmailActionsService.toggleStar(emailId: email.emailId, isStarred: newStarState, accessToken: accessToken)

                await MainActor.run {
                    self.emails = self.emails.map { email in
                        if email.emailId == email.emailId {
                            var updated = email
                            updated.isStarred = newStarState
                            return updated
                        }
                        return email
                    }
                }
            } catch {
                await MainActor.run {
                    self.errorMessage = "Failed to update star status: \(error.localizedDescription)"
                }
            }
        }
    }

    func deleteEmail(_ email: EmailItem) {
        Task {
            do {
                let accessToken = try await OAuthService.shared.getCurrentAccessToken()
                try await gmailActionsService.deleteEmail(emailId: email.emailId, accessToken: accessToken)

                await MainActor.run {
                    self.emails.removeAll { $0.emailId == email.emailId }
                }
            } catch {
                await MainActor.run {
                    self.errorMessage = "Failed to delete email: \(error.localizedDescription)"
                }
            }
        }
    }

    func deferEmail(_ email: EmailItem) {
        Task {
            do {
                let accessToken = try await OAuthService.shared.getCurrentAccessToken()
                try await gmailActionsService.deferEmail(emailId: email.emailId, accessToken: accessToken)

                await MainActor.run {
                    // Remove the email from the displayed list since it's now archived
                    self.emails.removeAll { $0.emailId == email.emailId }
                }
            } catch {
                await MainActor.run {
                    self.errorMessage = "Failed to defer email: \(error.localizedDescription)"
                }
            }
        }
    }

    func unsubscribe(from email: EmailItem) {
        Task {
            do {
                guard let unsubscribeUrl = email.unsubscribeUrl else {
                    await MainActor.run {
                        self.errorMessage = "No unsubscribe URL available for this email"
                    }
                    return
                }

                let accessToken = try await OAuthService.shared.getCurrentAccessToken()
                try await gmailActionsService.unsubscribe(emailId: email.emailId, unsubscribeUrl: unsubscribeUrl, accessToken: accessToken)

                await MainActor.run {
                    self.emails.removeAll { $0.emailId == email.emailId }
                    self.errorMessage = "Unsubscribed successfully"
                }
            } catch {
                await MainActor.run {
                    self.errorMessage = "Failed to unsubscribe: \(error.localizedDescription)"
                }
            }
        }
    }

    func summarizeEmail(_ email: EmailItem) {
        Task {
            do {
                let llm = LLMProviderFactory.shared.getSelectedProvider()
                let result = try await llm.summarizeEmail(
                    subject: email.subject,
                    sender: email.sender,
                    body: String(email.body.prefix(3000))
                )

                await MainActor.run {
                    self.emails = self.emails.map { email in
                        if email.emailId == email.emailId {
                            var updated = email
                            updated.summary = result.summaryPurpose
                            return updated
                        }
                        return email
                    }
                }
            } catch {
                await MainActor.run {
                    self.errorMessage = "Failed to summarize: \(error.localizedDescription)"
                }
            }
        }
    }
}
