import XCTest
final class LeaseTests: XCTestCase {
    func testTransportRejectsUntrustedEndpoints() {
        for value in ["http://example.com", "https://user:pass@example.com", "https://example.com/path", "https://example.com?token=x"] { XCTAssertThrowsError(try EndpointPolicy.root(value)) }
        XCTAssertNoThrow(try EndpointPolicy.root("https://example.com:4317"))
    }
    func testLeaseExpiryAndMissingAuthority() {
        let now = Date(timeIntervalSince1970: 100)
        XCTAssertTrue(InsertionLease(lease_id:"x",secret:"s",expires_at:100001,draft:"合成文字",person_name:"合成人物").valid(at:now))
        XCTAssertFalse(InsertionLease(lease_id:"x",secret:"s",expires_at:100000,draft:"合成文字",person_name:"合成人物").valid(at:now))
        XCTAssertFalse(InsertionLease(lease_id:"x",secret:"",expires_at:130000,draft:"合成文字",person_name:"合成人物").valid(at:now))
    }
}
