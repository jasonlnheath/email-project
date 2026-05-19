import XCTest
@testable import EmailAI

/// Tests for EmailPriorityCalculator (priority calculation logic)
final class EmailPriorityCalculatorTests: XCTestCase {

    // MARK: - VIP Priority Tests

    func testCalculateReturnsVIPHighWhenSenderIsVIPContact() {
        let vipContacts = [
            Contact(
                id: UUID(),
                email: "boss@company.com",
                name: "The Boss",
                phoneNumber: nil,
                photoUrl: nil,
                lastUpdated: Date()
            )
        ]

        let email = EmailItem(
            emailId: "1",
            subject: "Regular subject",
            sender: "boss@company.com",
            date: Date(),
            body: "Regular body",
            snippet: ""
        )

        let priority = EmailPriorityCalculator.calculate(for: email, vipContacts: vipContacts)
        XCTAssertEqual(priority, .vipHigh, "Should return VIP_HIGH when sender is a VIP contact")
    }

    func testCalculateReturnsVIPHighWhenSenderContainsVIPEmail() {
        let vipContacts = [
            Contact(
                id: UUID(),
                email: "ceo@company.com",
                name: "CEO",
                phoneNumber: nil,
                photoUrl: nil,
                lastUpdated: Date()
            )
        ]

        let email = EmailItem(
            emailId: "1",
            subject: "Regular subject",
            sender: "John CEO <ceo@company.com>",
            date: Date(),
            body: "Regular body",
            snippet: ""
        )

        let priority = EmailPriorityCalculator.calculate(for: email, vipContacts: vipContacts)
        XCTAssertEqual(priority, .vipHigh, "Should return VIP_HIGH when sender field contains VIP email")
    }

    // MARK: - High Priority Tests (Urgent Keywords)

    func testCalculateReturnsHighForUrgentKeyword() {
        let email = EmailItem(
            emailId: "1",
            subject: "URGENT: Server is down",
            sender: "devops@company.com",
            date: Date(),
            body: "Regular body",
            snippet: ""
        )

        let priority = EmailPriorityCalculator.calculate(for: email, vipContacts: [])
        XCTAssertEqual(priority, .high, "Should return HIGH for 'urgent' keyword in subject")
    }

    func testCalculateReturnsHighForASAPKeyword() {
        let email = EmailItem(
            emailId: "1",
            subject: "Response needed ASAP",
            sender: "colleague@company.com",
            date: Date(),
            body: "Regular body",
            snippet: ""
        )

        let priority = EmailPriorityCalculator.calculate(for: email, vipContacts: [])
        XCTAssertEqual(priority, .high, "Should return HIGH for 'asap' keyword in subject")
    }

    func testCalculateReturnsHighForDeadlineKeyword() {
        let email = EmailItem(
            emailId: "1",
            subject: "Project deadline tomorrow",
            sender: "manager@company.com",
            date: Date(),
            body: "Regular body",
            snippet: ""
        )

        let priority = EmailPriorityCalculator.calculate(for: email, vipContacts: [])
        XCTAssertEqual(priority, .high, "Should return HIGH for 'deadline' keyword in subject")
    }

    func testCalculateReturnsHighForMeetingKeyword() {
        let email = EmailItem(
            emailId: "1",
            subject: "Meeting invitation: Quarterly review",
            sender: "admin@company.com",
            date: Date(),
            body: "Regular body",
            snippet: ""
        )

        let priority = EmailPriorityCalculator.calculate(for: email, vipContacts: [])
        XCTAssertEqual(priority, .high, "Should return HIGH for 'meeting' keyword in subject")
    }

    func testCalculateReturnsHighForMixedCaseUrgent() {
        let email = EmailItem(
            emailId: "1",
            subject: "UrgEnT: Important issue",
            sender: "someone@company.com",
            date: Date(),
            body: "Regular body",
            snippet: ""
        )

        let priority = EmailPriorityCalculator.calculate(for: email, vipContacts: [])
        XCTAssertEqual(priority, .high, "Should be case-insensitive for urgent keywords")
    }

    // MARK: - Low Priority Tests (Newsletter Keywords)

    func testCalculateReturnsLowForUnsubscribeKeyword() {
        let email = EmailItem(
            emailId: "1",
            subject: "Weekly Update",
            sender: "newsletter@company.com",
            date: Date(),
            body: "Click here to unsubscribe from this newsletter",
            snippet: ""
        )

        let priority = EmailPriorityCalculator.calculate(for: email, vipContacts: [])
        XCTAssertEqual(priority, .low, "Should return LOW for 'unsubscribe' keyword in body")
    }

    func testCalculateReturnsLowForNewsletterKeyword() {
        let email = EmailItem(
            emailId: "1",
            subject: "Your weekly digest",
            sender: "news@site.com",
            date: Date(),
            body: "This is our newsletter content",
            snippet: ""
        )

        let priority = EmailPriorityCalculator.calculate(for: email, vipContacts: [])
        XCTAssertEqual(priority, .low, "Should return LOW for 'newsletter' keyword in body")
    }

    func testCalculateReturnsLowForPromotionKeyword() {
        let email = EmailItem(
            emailId: "1",
            subject: "Special offer just for you",
            sender: "deals@shop.com",
            date: Date(),
            body: "Check out our promotion and discount deals",
            snippet: ""
        )

        let priority = EmailPriorityCalculator.calculate(for: email, vipContacts: [])
        XCTAssertEqual(priority, .low, "Should return LOW for promotion keywords in body")
    }

    // MARK: - Medium Priority Tests (Default)

    func testCalculateReturnsMediumForNormalEmail() {
        let email = EmailItem(
            emailId: "1",
            subject: "Regular email about project",
            sender: "colleague@company.com",
            date: Date(),
            body: "Just checking in on the project status",
            snippet: ""
        )

        let priority = EmailPriorityCalculator.calculate(for: email, vipContacts: [])
        XCTAssertEqual(priority, .medium, "Should return MEDIUM for normal emails without special keywords")
    }

    // MARK: - Priority Color Tests

    func testColorReturnsGoldForVIPHigh() {
        let color = EmailPriorityCalculator.color(for: .vipHigh)
        // Check RGB values approximately
        var red: CGFloat = 0
        var green: CGFloat = 0
        var blue: CGFloat = 0
        var alpha: CGFloat = 0

        color.getRed(&red, green: &green, blue: &blue, alpha: &alpha)

        XCTAssertEqual(red, 1.0, accuracy: 0.01, "Red should be 1.0 for VIP_HIGH")
        XCTAssertEqual(green, 0.84, accuracy: 0.01, "Green should be 0.84 for VIP_HIGH (gold)")
        XCTAssertEqual(blue, 0.0, accuracy: 0.01, "Blue should be 0.0 for VIP_HIGH")
    }

    func testColorReturnsRedForHigh() {
        let color = EmailPriorityCalculator.color(for: .high)
        XCTAssertEqual(color, .red, "Should return red color for HIGH priority")
    }

    func testColorReturnsPurpleForMedium() {
        let color = EmailPriorityCalculator.color(for: .medium)
        XCTAssertEqual(color, .purple, "Should return purple color for MEDIUM priority")
    }

    func testColorReturnsGrayForLow() {
        let color = EmailPriorityCalculator.color(for: .low)
        XCTAssertEqual(color, .gray, "Should return gray color for LOW priority")
    }

    // MARK: - Background Color Tests

    func testBackgroundColorReturnsLightGoldForVIPHigh() {
        let bgColor = EmailPriorityCalculator.backgroundColor(for: .vipHigh)

        var red: CGFloat = 0
        var green: CGFloat = 0
        var blue: CGFloat = 0
        var alpha: CGFloat = 0

        bgColor.getRed(&red, green: &green, blue: &blue, alpha: &alpha)

        XCTAssertEqual(red, 1.0, accuracy: 0.01, "Red should be 1.0 for VIP_HIGH background")
        XCTAssertEqual(green, 0.92, accuracy: 0.01, "Green should be 0.92 for VIP_HIGH background (light gold)")
        XCTAssertEqual(blue, 0.23, accuracy: 0.01, "Blue should be 0.23 for VIP_HIGH background")
    }

    func testBackgroundColorReturnsSemiTransparentRedForHigh() {
        let bgColor = EmailPriorityCalculator.backgroundColor(for: .high)

        var red: CGFloat = 0
        var green: CGFloat = 0
        var blue: CGFloat = 0
        var alpha: CGFloat = 0

        UIColor(bgColor).getRed(&red, green: &green, blue: &blue, alpha: &alpha)

        XCTAssertEqual(alpha, 0.2, accuracy: 0.01, "Alpha should be 0.2 for HIGH background")
    }

    // MARK: - Priority Override Tests

    func testVIPObservesUrgentKeyword() {
        let vipContacts = [
            Contact(
                id: UUID(),
                email: "boss@company.com",
                name: "Boss",
                phoneNumber: nil,
                photoUrl: nil,
                lastUpdated: Date()
            )
        ]

        let email = EmailItem(
            emailId: "1",
            subject: "URGENT: Something",
            sender: "boss@company.com",
            date: Date(),
            body: "Body",
            snippet: ""
        )

        let priority = EmailPriorityCalculator.calculate(for: email, vipContacts: vipContacts)
        XCTAssertEqual(priority, .vipHigh, "VIP should override urgent keywords")
    }

    func testUrgentOverridesNewsletter() {
        let email = EmailItem(
            emailId: "1",
            subject: "URGENT: Important newsletter update",
            sender: "news@company.com",
            date: Date(),
            body: "Click here to unsubscribe from our newsletter",
            snippet: ""
        )

        let priority = EmailPriorityCalculator.calculate(for: email, vipContacts: [])
        XCTAssertEqual(priority, .high, "Urgent keyword in subject should override newsletter keywords in body")
    }

    // MARK: - Edge Cases

    func testCalculateHandlesEmptyContactList() {
        let email = EmailItem(
            emailId: "1",
            subject: "Test",
            sender: "test@example.com",
            date: Date(),
            body: "Test body",
            snippet: ""
        )

        let priority = EmailPriorityCalculator.calculate(for: email, vipContacts: [])
        // Should not crash and should return a valid priority
        XCTAssertEqual(priority, .medium, "Should handle empty contact list gracefully")
    }

    func testCalculateHandlesEmptySubjectAndBody() {
        let email = EmailItem(
            emailId: "1",
            subject: "",
            sender: "test@example.com",
            date: Date(),
            body: "",
            snippet: ""
        )

        let priority = EmailPriorityCalculator.calculate(for: email, vipContacts: [])
        XCTAssertEqual(priority, .medium, "Should handle empty subject and body gracefully")
    }
}
