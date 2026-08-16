import os
import re

def create_report(source_path, target_path, role_filter_val, title):
    with open(source_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # 1. Rename Component
    component_name = "ReportAsn" if role_filter_val == "asn" else "ReportNonAsn"
    content = content.replace("const Dashboard = () => {", f"const {component_name} = () => {{")
    content = content.replace("export default Dashboard;", f"export default {component_name};")
    
    # 2. Hardcode role_filter
    content = content.replace("const [roleFilter, setRoleFilter] = useState(''); // '', 'asn', 'non_asn'", "")
    content = content.replace("if (roleFilter) params.append('role_filter', roleFilter);", f"params.append('role_filter', '{role_filter_val}');")
    content = content.replace(", roleFilter", "") # Remove from dependencies
    
    # 3. Remove Kegiatan filter state
    content = content.replace("  const [kegiatanList, setKegiatanList] = useState([]);\n", "")
    content = content.replace("  const [selectedKegiatanId, setSelectedKegiatanId] = useState('');\n", "")
    content = content.replace("if (selectedKegiatanId) params.append('kegiatan_id', selectedKegiatanId);", "")
    content = content.replace(", selectedKegiatanId", "") # Remove from dependencies
    content = content.replace("setKegiatanList", "pass") # if any
    
    # 4. Remove useEffect for kegiatanList
    content = re.sub(r'  // Fetch kegiatan list for filter dropdown\n\s*useEffect\(\(\) => \{\n.*?\n\s*\}, \[\]\);\n', '', content, flags=re.DOTALL)
    
    # 5. Handle Reset Filters
    content = content.replace("setSelectedKegiatanId(''); setRoleFilter('');", "")
    
    # 6. Change Title
    content = content.replace('Laporan Presensi ASN', title)
    
    # 7. Remove UI filters
    # Remove Kegiatan Filter block
    kegiatan_ui_regex = r'<div className="min-w-\[200px\]">\s*<label.*?Filter Kegiatan.*?</label>.*?</div>\s*</div>'
    content = re.sub(kegiatan_ui_regex, '', content, flags=re.DOTALL)
    
    # Remove Tipe Pegawai Filter block
    tipe_pegawai_ui_regex = r'<div className="min-w-\[150px\]">\s*<label.*?Tipe Pegawai.*?</label>.*?</div>\s*</div>'
    content = re.sub(tipe_pegawai_ui_regex, '', content, flags=re.DOTALL)
    
    # Fix active filters condition
    content = content.replace("const hasActiveFilters = searchQuery || startDate || endDate || statusFilter || selectedKegiatanId;", "const hasActiveFilters = searchQuery || startDate || endDate || statusFilter;")
    content = content.replace("const hasActiveFilters = searchQuery || startDate || endDate || statusFilter ||  || ;", "const hasActiveFilters = searchQuery || startDate || endDate || statusFilter;")
    content = content.replace("const hasActiveFilters = searchQuery || startDate || endDate || statusFilter ||  ||", "const hasActiveFilters = searchQuery || startDate || endDate || statusFilter")
    
    with open(target_path, 'w', encoding='utf-8') as f:
        f.write(content)

src = r"c:\Users\ASUS\Web_Face_Recognation\src\pages\Dashboard.jsx"
create_report(src, r"c:\Users\ASUS\Web_Face_Recognation\src\pages\ReportAsn.jsx", "asn", "Laporan Presensi Harian - ASN")
create_report(src, r"c:\Users\ASUS\Web_Face_Recognation\src\pages\ReportNonAsn.jsx", "non_asn", "Laporan Presensi Harian - Non-ASN")

print("Files generated.")
