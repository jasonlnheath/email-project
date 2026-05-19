import Foundation
import GRDB

/// Shared database instance
actor ContactDatabase {
    static let shared = ContactDatabase()

    private var db: DatabaseQueue
    private let path: String

    private init() {
        // Database file path
        let fileURL = try! FileManager.default
            .url(for: .documentDirectory, in: .userDomainMask, appropriateFor: nil, create: true)
            .appendingPathComponent("EmailAI.sqlite")
        self.path = fileURL.path
        self.db = try! DatabaseQueue(path: self.path)
    }

    /// Create database schema
    func createSchema() throws {
        try db.write { db in
            // Contacts table
            try db.create(table: "contacts") { t in
                t.column("id", .integer).primaryKey(autoincrement: true)
                t.column("email", .text).notNull().unique()
                t.column("name", .text)
                t.column("displayName", .text)
                t.column("phone", .text)
                t.column("photoUrl", .text)
                t.column("source", .text).notNull().defaults(to: ContactSource.manual.rawValue)
                t.column("company", .text)
                t.column("title", .text)
                t.column("location", .text)
                t.column("linkedinUrl", .text)
                t.column("twitterUrl", .text)
                t.column("notes", .text)
                t.column("overallScore", .double).defaults(to: 0.0)
            }

            // VIP contacts table
            try db.create(table: "vip_contacts") { t in
                t.column("contactId", .integer).primaryKey().references("contacts", column: "id", onDelete: .cascade)
                t.column("relationshipType", .text).notNull().defaults(to: RelationshipType.vip.rawValue)
                t.column("relationshipScore", .integer).notNull().defaults(to: 8)
                t.column("isPushEnabled", .boolean).notNull().defaults(to: true)
                t.column("isPullEnabled", .boolean).notNull().defaults(to: true)
                t.column("frequencyScore", .double).notNull().defaults(to: 0.0)
            }

            // Contact attributes table
            try db.create(table: "contact_attributes") { t in
                t.autoIncrementedPrimaryKey("id")
                t.column("contactId", .integer).notNull().references("contacts", column: "id", onDelete: .cascade)
                t.column("type", .text).notNull()
                t.column("value", .text).notNull()
                t.uniqueKey(["contactId", "type", "value"])
            }
        }

        print("✅ Database schema created at: \(path)")
    }

    // MARK: - Contact Operations

    /// Insert or update a contact
    func upsertContact(_ contact: RichContact) throws {
        try db.write { db in
            var mutableContact = contact

            // Upsert contact
            try mutableContact.insert(db, onConflict: .ignore)

            // Get the contact ID
            let contactId: Int64?
            if let existingId = mutableContact.id {
                contactId = existingId
            } else {
                contactId = try Int64.fetchOne(db, sql: "SELECT id FROM contacts WHERE email = ?", arguments: [mutableContact.email])
            }

            guard let id = contactId else { return }

            // Handle VIP info
            if let vipInfo = mutableContact.vipInfo {
                try db.execute(
                    sql: "INSERT OR REPLACE INTO vip_contacts (contactId, relationshipType, relationshipScore, isPushEnabled, isPullEnabled, frequencyScore) VALUES (?, ?, ?, ?, ?, ?)",
                  arguments: [id, vipInfo.relationshipType.rawValue, vipInfo.relationshipScore, vipInfo.isPushEnabled, vipInfo.isPullEnabled, vipInfo.frequencyScore]
                )
            }

            // Handle attributes
            for var attribute in mutableContact.attributes {
                attribute.contactId = id
                try attribute.insert(db, onConflict: .ignore)
            }
        }
    }

    /// Get all contacts
    func getAllContacts() throws -> [RichContact] {
        try db.read { db in
            try RichContact.fetchAll(db, sql: "SELECT * FROM contacts ORDER BY name COLLATE NOCASE")
        }
    }

    /// Get contact by email
    func getContact(byEmail email: String) throws -> RichContact? {
        try db.read { db in
            try RichContact.fetchOne(db, key: email)
        }
    }

    /// Get VIP contacts
    func getVIPContacts() throws -> [RichContact] {
        try db.read { db in
            let sql = """
                SELECT c.* FROM contacts c
                INNER JOIN vip_contacts v ON c.id = v.contactId
                WHERE v.isPushEnabled = 1
                ORDER BY v.relationshipScore DESC
            """
            return try RichContact.fetchAll(db, sql: sql)
        }
    }

    /// Search contacts by name or email
    func searchContacts(_ query: String) throws -> [RichContact] {
        try db.read { db in
            let sql = """
                SELECT * FROM contacts
                WHERE name LIKE ? OR email LIKE ? OR displayName LIKE ?
                ORDER BY name COLLATE NOCASE
                LIMIT 50
            """
            let pattern = "%\(query)%"
            return try RichContact.fetchAll(db, sql: sql, arguments: [pattern, pattern, pattern])
        }
    }

    /// Delete contact by email
    func deleteContact(email: String) throws {
        try db.write { db in
            try db.execute(sql: "DELETE FROM contacts WHERE email = ?", arguments: [email])
        }
    }

    /// Get contact count
    func getContactCount() throws -> Int {
        try db.read { db in
            try Int.fetchOne(db, sql: "SELECT COUNT(*) FROM contacts") ?? 0
        }
    }
}
