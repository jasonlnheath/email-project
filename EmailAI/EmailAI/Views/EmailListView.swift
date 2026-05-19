import SwiftUI

struct EmailListView: View {
    @EnvironmentObject var viewModel: EmailListViewModel

    var body: some View {
        NavigationStack {
            Group {
                if viewModel.emails.isEmpty {
                    VStack(spacing: 12) {
                        Image(systemName: "envelope.badge")
                            .font(.system(size: 40))
                            .foregroundStyle(.secondary)
                        Text("No Emails")
                            .font(.title2)
                        Text("Tap the fetch button to load emails from Gmail")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                } else {
                    ScrollView {
                        LazyVStack(spacing: 12) {
                            ForEach(viewModel.emails.indices, id: \.self) { index in
                                ExpandableEmailRow(
                                    email: $viewModel.emails[index],
                                    onSummarize: {
                                        viewModel.summarizeEmail(viewModel.emails[index])
                                    },
                                    onOpenGmail: {
                                        if let url = URL(string: viewModel.emails[index].gmailUrl) {
                                            UIApplication.shared.open(url)
                                        }
                                    },
                                    onToggleRead: {
                                        viewModel.toggleRead(for: viewModel.emails[index])
                                    },
                                    onToggleStar: {
                                        viewModel.toggleStar(for: viewModel.emails[index])
                                    },
                                    onDelete: {
                                        viewModel.deleteEmail(viewModel.emails[index])
                                    },
                                    onDefer: {
                                        viewModel.deferEmail(viewModel.emails[index])
                                    },
                                    onUnsubscribe: {
                                        if viewModel.emails[index].unsubscribeUrl != nil {
                                            viewModel.unsubscribe(from: viewModel.emails[index])
                                        }
                                    }
                                )
                            }
                        }
                        .padding()
                    }
                }
            }
            .navigationTitle("Emails")
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(action: { viewModel.fetchEmails() }) {
                        if viewModel.isFetching {
                            ProgressView()
                        } else {
                            Label("Fetch", systemImage: "arrow.clockwise")
                        }
                    }
                    .disabled(viewModel.isFetching)
                }
            }
            .overlay(alignment: .bottom) {
                if let errorMessage = viewModel.errorMessage {
                    Text(errorMessage)
                        .foregroundStyle(.red)
                        .font(.caption)
                        .padding()
                }
            }
        }
    }
}

struct EmailRow: View {
    let email: EmailItem

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(email.subject)
                .font(.headline)
                .lineLimit(1)
            HStack {
                Text(email.sender)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                Spacer()
                Text(email.date, style: .date)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Text(email.snippet.isEmpty ? email.body : email.snippet)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(2)
        }
        .padding(.vertical, 2)
    }
}

struct EmailListView_Previews: PreviewProvider {
    static var previews: some View {
        EmailListView()
            .environmentObject(EmailListViewModel())
    }
}

/// Expandable email row component with priority border and inline actions
struct ExpandableEmailRow: View {
    @Binding var email: EmailItem
    var onSummarize: () -> Void
    var onOpenGmail: () -> Void
    var onToggleRead: () -> Void
    var onToggleStar: () -> Void
    var onDelete: () -> Void
    var onDefer: () -> Void
    var onUnsubscribe: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Collapsible header
            HStack(alignment: .top, spacing: 12) {
                // Priority indicator
                Rectangle()
                    .fill(EmailPriorityCalculator.color(for: email.priority))
                    .frame(width: 4)
                    .frame(height: 80)

                // Email content
                VStack(alignment: .leading, spacing: 6) {
                    // Header row with subject and expand icon
                    HStack {
                        Text(email.subject)
                            .font(.headline)
                            .lineLimit(2)
                            .strikethrough(email.isRead, color: .gray)

                        Spacer()

                        // Expand/collapse icon
                        Image(systemName: email.isExpanded ? "chevron.up" : "chevron.down")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }

                    // Sender and date
                    HStack {
                        Text(email.sender)
                            .font(.subheadline)
                            .foregroundColor(.secondary)
                            .lineLimit(1)

                        Spacer()

                        Text(formattedDate(email.date))
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }

                    // VIP badge
                    if let vipInfo = email.vipInfo {
                        HStack(spacing: 4) {
                            Image(systemName: "star.fill")
                                .font(.caption2)
                                .foregroundColor(.yellow)
                            Text(vipInfo.name)
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }

                    // Priority badge
                    Text(email.priority.displayName)
                        .font(.caption2)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 2)
                        .background(EmailPriorityCalculator.backgroundColor(for: email.priority))
                        .foregroundColor(EmailPriorityCalculator.color(for: email.priority))
                        .cornerRadius(4)
                }
                .padding(.vertical, 12)
                .padding(.trailing, 12)
                .contentShape(Rectangle())
                .onTapGesture {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        email.isExpanded.toggle()
                    }
                }
            }

            // Expandable content
            if email.isExpanded {
                Divider()
                    .padding(.leading, 16)

                VStack(alignment: .leading, spacing: 12) {
                    // Summary section
                    if let summary = email.summary, !summary.isEmpty {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("Summary")
                                .font(.subheadline)
                                .fontWeight(.semibold)
                            Text(summary)
                                .font(.body)
                                .foregroundColor(.secondary)
                        }
                        .padding(.horizontal, 16)
                        .padding(.top, 8)
                    }

                    // Action buttons
                    HStack(spacing: 12) {
                        // Read/Unread button
                        Button(action: onToggleRead) {
                            Label(
                                email.isRead ? "Mark Unread" : "Mark Read",
                                systemImage: email.isRead ? "envelope.badge.fill" : "envelope.open.fill"
                            )
                            .font(.caption)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 6)
                            .background(Color.blue.opacity(0.1))
                            .foregroundColor(.blue)
                            .cornerRadius(6)
                        }

                        // Star button
                        Button(action: onToggleStar) {
                            Label(
                                email.isStarred ? "Unstar" : "Star",
                                systemImage: email.isStarred ? "star.fill" : "star"
                            )
                            .font(.caption)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 6)
                            .background(Color.yellow.opacity(0.1))
                            .foregroundColor(.yellow)
                            .cornerRadius(6)
                        }

                        // Defer button
                        Button(action: onDefer) {
                            Label("Defer", systemImage: "clock")
                                .font(.caption)
                                .padding(.horizontal, 12)
                                .padding(.vertical, 6)
                                .background(Color.orange.opacity(0.1))
                                .foregroundColor(.orange)
                                .cornerRadius(6)
                        }

                        // Delete button
                        Button(action: onDelete) {
                            Label("Delete", systemImage: "trash")
                                .font(.caption)
                                .padding(.horizontal, 12)
                                .padding(.vertical, 6)
                                .background(Color.red.opacity(0.1))
                                .foregroundColor(.red)
                                .cornerRadius(6)
                        }

                        // Unsubscribe button (only if unsubscribe URL exists)
                        if email.unsubscribeUrl != nil {
                            Button(action: onUnsubscribe) {
                                Label("Unsubscribe", systemImage: "minus.circle")
                                    .font(.caption)
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 6)
                                    .background(Color.gray.opacity(0.1))
                                    .foregroundColor(.gray)
                                    .cornerRadius(6)
                            }
                        }

                        // Open in Gmail button
                        Button(action: onOpenGmail) {
                            Label("Open", systemImage: "arrow.up.right.square")
                                .font(.caption)
                                .padding(.horizontal, 12)
                                .padding(.vertical, 6)
                                .background(Color.gray.opacity(0.1))
                                .foregroundColor(.primary)
                                .cornerRadius(6)
                        }

                        // Summarize button (only if no summary)
                        if email.summary == nil {
                            Button(action: onSummarize) {
                                Label("Summarize", systemImage: "sparkles")
                                    .font(.caption)
                                    .padding(.horizontal, 12)
                                    .padding(.vertical, 6)
                                    .background(Color.purple.opacity(0.1))
                                    .foregroundColor(.purple)
                                    .cornerRadius(6)
                            }
                        }

                        Spacer()
                    }
                    .padding(.horizontal, 16)
                    .padding(.bottom, 8)
                }
                .transition(.opacity.combined(with: .move(edge: .top)))
            }
        }
        .background(Color(.systemBackground))
        .cornerRadius(8)
        .shadow(color: Color.black.opacity(0.05), radius: 2, x: 0, y: 1)
    }

    private func formattedDate(_ date: Date) -> String {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .short
        return formatter.localizedString(for: date, relativeTo: Date())
    }
}

// MARK: - Dashboard

/// ViewModel for Dashboard - shows unread emails sorted by priority
@MainActor
class DashboardViewModel: ObservableObject {
    @Published var emails: [EmailItem] = []
    @Published var isFetching = false
    @Published var errorMessage: String?
    @Published var isSignedIn = false
    @Published var totalUnreadCount: Int = 0
    @Published var selectedEmail: EmailItem?

    private let gmailService = GmailService()
    private let contactsService = ContactsService.shared
    private var vipContacts: [Contact] = []

    init() {
        Task {
            isSignedIn = await OAuthService.shared.isSignedIn
        }
    }

    /// Fetch only unread emails, sorted by priority
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

                // Fetch all emails from Gmail
                let gmailMessages = try await self.gmailService.fetchEmails(accessToken: accessToken)

                // Convert to EmailItem models
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
                        priority: .medium,
                        unsubscribeUrl: message.unsubscribeUrl
                    )

                    // Calculate priority
                    let priority = EmailPriorityCalculator.calculate(for: emailItem, vipContacts: contacts)
                    var updatedItem = emailItem
                    updatedItem.priority = priority

                    // Set VIP info if applicable
                    if let vip = contacts.first(where: { emailItem.sender.contains($0.email) }) {
                        updatedItem.vipInfo = VIPInfo(name: vip.name ?? "Unknown", relationshipType: "VIP")
                    }

                    return updatedItem
                }

                // Filter for unread emails, then sort by priority
                let filteredAndSorted = items
                    .filter { !$0.isRead }
                    .sorted { email1, email2 in
                        // Sort by priority first
                        let priorityOrder: [EmailPriority] = [.vipHigh, .high, .medium, .low]
                        let priority1Index = priorityOrder.firstIndex(of: email1.priority) ?? 3
                        let priority2Index = priorityOrder.firstIndex(of: email2.priority) ?? 3

                        if priority1Index != priority2Index {
                            return priority1Index < priority2Index
                        }

                        // Within same priority, sort by date (newest first)
                        return email1.date > email2.date
                    }

                await MainActor.run {
                    self.emails = filteredAndSorted
                    self.totalUnreadCount = filteredAndSorted.count
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

    /// Generate summary for selected email
    func generateSummary(for email: EmailItem) {
        Task {
            do {
                print("=== Generating summary for email: \(email.subject) ===")
                print("Body length: \(email.body.count)")
                print("Body preview: \(String(email.body.prefix(200)))")

                let llm = LLMProviderFactory.shared.getSelectedProvider()
                let result = try await llm.summarizeEmail(
                    subject: email.subject,
                    sender: email.sender,
                    body: String(email.body.prefix(3000))
                )

                print("Summary generated: \(result.summaryPurpose.prefix(100))...")
                print("Key entities: \(result.keyEntities)")
                print("Action items: \(result.actionItems)")

                await MainActor.run {
                    self.emails = self.emails.map { item in
                        if item.emailId == email.emailId {
                            var updated = item
                            updated.summary = result.summaryPurpose
                            return updated
                        }
                        return item
                    }

                    // Update selected email to show summary
                    if self.selectedEmail?.emailId == email.emailId {
                        var updatedSelected = email
                        updatedSelected.summary = result.summaryPurpose
                        self.selectedEmail = updatedSelected
                    }
                }
            } catch {
                await MainActor.run {
                    self.errorMessage = "Failed to summarize: \(error.localizedDescription)"
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
                let gmailActionsService = GmailActionsService()

                if newReadState {
                    try await gmailActionsService.markAsRead(emailId: email.emailId, accessToken: accessToken)
                } else {
                    try await gmailActionsService.markAsUnread(emailId: email.emailId, accessToken: accessToken)
                }

                await MainActor.run {
                    // Update or remove from list based on new state
                    if newReadState {
                        // If marked as read, remove from dashboard
                        self.emails.removeAll { $0.emailId == email.emailId }
                        self.totalUnreadCount = max(0, self.totalUnreadCount - 1)
                    } else {
                        // Update the email
                        self.emails = self.emails.map { item in
                            if item.emailId == email.emailId {
                                var updated = item
                                updated.isRead = newReadState
                                return updated
                            }
                            return item
                        }
                    }

                    // Update selected email if it's the one we just modified
                    if self.selectedEmail?.emailId == email.emailId {
                        var updated = email
                        updated.isRead = newReadState
                        self.selectedEmail = updated
                    }
                }
            } catch {
                await MainActor.run {
                    self.errorMessage = "Failed to update read status: \(error.localizedDescription)"
                }
            }
        }
    }

    func deleteEmail(_ email: EmailItem) {
        Task {
            do {
                let accessToken = try await OAuthService.shared.getCurrentAccessToken()
                let gmailActionsService = GmailActionsService()

                try await gmailActionsService.deleteEmail(emailId: email.emailId, accessToken: accessToken)

                await MainActor.run {
                    self.emails.removeAll { $0.emailId == email.emailId }
                    self.totalUnreadCount = max(0, self.totalUnreadCount - 1)
                    self.selectedEmail = nil
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
                let gmailActionsService = GmailActionsService()

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
                let gmailActionsService = GmailActionsService()

                try await gmailActionsService.unsubscribe(emailId: email.emailId, unsubscribeUrl: unsubscribeUrl, accessToken: accessToken)

                await MainActor.run {
                    self.emails.removeAll { $0.emailId == email.emailId }
                    self.totalUnreadCount = max(0, self.totalUnreadCount - 1)
                    self.selectedEmail = nil
                    self.errorMessage = "Unsubscribed successfully"
                }
            } catch {
                await MainActor.run {
                    self.errorMessage = "Failed to unsubscribe: \(error.localizedDescription)"
                }
            }
        }
    }
}

/// Dashboard for quick processing of unread emails
struct DashboardView: View {
    @StateObject private var viewModel = DashboardViewModel()
    @State private var selectedEmailId: String?

    var body: some View {
        NavigationSplitView {
            // Email list
            Group {
                if viewModel.emails.isEmpty && !viewModel.isFetching {
                    emptyStateView
                } else {
                    emailListView
                }
            }
            .navigationTitle("Dashboard")
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) {
                    if viewModel.totalUnreadCount > 0 {
                        HStack(spacing: 4) {
                            Circle()
                                .fill(Color.red)
                                .frame(width: 8, height: 8)
                            Text("\(viewModel.totalUnreadCount)")
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                }

                ToolbarItem(placement: .navigationBarTrailing) {
                    Button(action: { viewModel.fetchEmails() }) {
                        if viewModel.isFetching {
                            ProgressView()
                        } else {
                            Label("Fetch", systemImage: "arrow.clockwise")
                        }
                    }
                    .disabled(viewModel.isFetching)
                }
            }
            .overlay(alignment: .bottom) {
                if let errorMessage = viewModel.errorMessage {
                    Text(errorMessage)
                        .foregroundStyle(.red)
                        .font(.caption)
                        .padding()
                        .background(Color(.systemBackground))
                        .cornerRadius(8)
                        .shadow(radius: 2)
                        .padding()
                }
            }
        } detail: {
            // Detail view (email opens to right)
            Group {
                if let emailId = selectedEmailId,
                   let email = viewModel.emails.first(where: { $0.emailId == emailId }) {
                    EmailDetailContentView(email: email)
                } else {
                    Text("Select an email to view")
                        .foregroundStyle(.secondary)
                        .navigationTitle("Email")
                }
            }
        }
        .onAppear {
            if viewModel.emails.isEmpty {
                viewModel.fetchEmails()
            }
        }
    }

    private var emptyStateView: some View {
        VStack(spacing: 12) {
            Image(systemName: "tray.full")
                .font(.system(size: 40))
                .foregroundStyle(.secondary)
            Text("All Caught Up!")
                .font(.title2)
            Text("No unread emails to process")
                .font(.subheadline)
                .foregroundStyle(.secondary)
            Button("Refresh") {
                viewModel.fetchEmails()
            }
            .buttonStyle(.bordered)
        }
    }

    private var emailListView: some View {
        ScrollView {
            LazyVStack(spacing: 12) {
                ForEach(viewModel.emails.indices, id: \.self) { index in
                    DashboardEmailCard(
                        email: $viewModel.emails[index],
                        onToggleRead: {
                            viewModel.toggleRead(for: viewModel.emails[index])
                        },
                        onOpen: {
                            // Open directly in Gmail instead of detail view
                            if let url = URL(string: viewModel.emails[index].gmailUrl) {
                                UIApplication.shared.open(url)
                                // Remove from dashboard after opening
                                viewModel.emails.removeAll { $0.emailId == viewModel.emails[index].emailId }
                            }
                        },
                        onDelete: {
                            viewModel.deleteEmail(viewModel.emails[index])
                        },
                        onDefer: {
                            viewModel.deferEmail(viewModel.emails[index])
                        },
                        onUnsubscribe: {
                            if viewModel.emails[index].unsubscribeUrl != nil {
                                viewModel.unsubscribe(from: viewModel.emails[index])
                            }
                        },
                        onGenerateSummary: {
                            viewModel.generateSummary(for: viewModel.emails[index])
                        }
                    )
                }
            }
            .padding()
        }
    }
}

/// Compact email card for dashboard processing
struct DashboardEmailCard: View {
    @Binding var email: EmailItem
    var onToggleRead: () -> Void
    var onOpen: () -> Void
    var onDelete: () -> Void
    var onDefer: () -> Void
    var onUnsubscribe: () -> Void
    var onGenerateSummary: () -> Void

    var body: some View {
        HStack(spacing: 0) {
            // Full-height priority color strip
            Rectangle()
                .fill(EmailPriorityCalculator.color(for: email.priority))
                .frame(width: 6)

            VStack(alignment: .leading, spacing: 0) {
                // Header - tappable for expand/collapse
                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text(email.subject)
                            .font(.headline)
                            .lineLimit(2)
                        Spacer()
                        HStack(spacing: 4) {
                            Text(formattedDate(email.date))
                                .font(.caption2)
                                .foregroundColor(.secondary)
                            Image(systemName: email.isExpanded ? "chevron.down" : "chevron.right")
                                .font(.caption2)
                                .foregroundColor(.secondary)
                        }
                    }

                    HStack {
                        Text(email.sender)
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .lineLimit(1)

                        Spacer()

                        // VIP badge
                        if email.vipInfo != nil {
                            HStack(spacing: 2) {
                                Image(systemName: "star.fill")
                                    .font(.caption2)
                                    .foregroundColor(.yellow)
                            }
                        }

                        // Priority badge
                        Text(email.priority.displayName)
                            .font(.caption2)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 2)
                            .background(EmailPriorityCalculator.backgroundColor(for: email.priority))
                            .foregroundColor(EmailPriorityCalculator.color(for: email.priority))
                            .cornerRadius(3)
                    }
                }
                .padding(12)
                .contentShape(Rectangle())
                .onTapGesture {
                    withAnimation(.easeInOut(duration: 0.2)) {
                        email.isExpanded.toggle()
                        if email.isExpanded && email.summary == nil {
                            onGenerateSummary()
                        }
                    }
                }

                // Expanded section - shows only summary
                if email.isExpanded {
                    Divider()

                    VStack(alignment: .leading, spacing: 8) {
                        if let summary = email.summary {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("Summary")
                                    .font(.subheadline)
                                    .fontWeight(.semibold)
                                    .foregroundColor(.secondary)
                                Text(summary)
                                    .font(.body)
                            }
                            .padding(.horizontal, 12)
                            .padding(.vertical, 8)
                        } else {
                            HStack(spacing: 8) {
                                ProgressView()
                                    .scaleEffect(0.7)
                                Text("Generating summary...")
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                            .padding(.horizontal, 12)
                            .padding(.vertical, 8)
                        }
                    }
                    .transition(.opacity.combined(with: .move(edge: .top)))
                }

                Divider()

                // Full-width action buttons
                VStack(spacing: 0) {
                    HStack(spacing: 0) {
                        DashboardActionButton(
                            title: email.isRead ? "Mark Unread" : "Mark Read",
                            icon: email.isRead ? "envelope.badge.fill" : "envelope.open.fill",
                            color: .blue,
                            action: onToggleRead
                        )

                        DashboardActionButton(
                            title: "Open",
                            icon: "arrow.up.right.square",
                            color: .green,
                            action: onOpen
                        )

                        DashboardActionButton(
                            title: "Defer",
                            icon: "clock",
                            color: .orange,
                            action: onDefer
                        )

                        DashboardActionButton(
                            title: "Delete",
                            icon: "trash",
                            color: .red,
                            action: onDelete
                        )
                    }

                    if email.unsubscribeUrl != nil {
                        DashboardActionButton(
                            title: "Unsubscribe",
                            icon: "minus.circle",
                            color: .gray,
                            action: onUnsubscribe
                        )
                    }
                }
            }
        }
        .background(Color(.systemBackground))
        .cornerRadius(8)
        .shadow(color: Color.black.opacity(0.05), radius: 2, x: 0, y: 1)
    }

    private func formattedDate(_ date: Date) -> String {
        let formatter = RelativeDateTimeFormatter()
        formatter.unitsStyle = .short
        return formatter.localizedString(for: date, relativeTo: Date())
    }
}

/// Full-width action button for dashboard
struct DashboardActionButton: View {
    let title: String
    let icon: String
    let color: Color
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Image(systemName: icon)
                    .font(.caption)
                Text(title)
                    .font(.caption)
                    .fontWeight(.medium)
            }
            .foregroundColor(color)
            .frame(maxWidth: .infinity)
            .padding(.vertical, 10)
            .background(color.opacity(0.12))
        }
        .buttonStyle(PlainButtonStyle())
    }
}

/// Inline email detail view (iOS Mail style)
struct EmailDetailContentView: View {
    let email: EmailItem

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                // Subject
                Text(email.subject)
                    .font(.title2)
                    .fontWeight(.bold)

                // Sender info
                HStack {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(email.sender)
                            .font(.headline)
                        Text(formattedDate(email.date))
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }

                    Spacer()

                    if let vipInfo = email.vipInfo {
                        HStack(spacing: 4) {
                            Image(systemName: "star.fill")
                                .foregroundColor(.yellow)
                            Text(vipInfo.name)
                                .font(.caption)
                                .foregroundColor(.secondary)
                        }
                    }
                }

                Divider()

                // Summary (if available)
                if let summary = email.summary {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("Summary")
                            .font(.subheadline)
                            .fontWeight(.semibold)
                        Text(summary)
                            .font(.body)
                    }
                    .padding()
                    .background(Color.purple.opacity(0.1))
                    .cornerRadius(8)
                }

                // Email body
                Text(email.body)
                    .font(.body)
            }
            .padding()
        }
        .navigationTitle("Email")
        .navigationBarTitleDisplayMode(.inline)
    }

    private func formattedDate(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateStyle = .medium
        formatter.timeStyle = .short
        return formatter.string(from: date)
    }
}
