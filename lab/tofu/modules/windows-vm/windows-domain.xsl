<?xml version="1.0"?>
<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
  <xsl:output method="xml" indent="yes"/>
  <xsl:template match="@*|node()">
    <xsl:copy><xsl:apply-templates select="@*|node()"/></xsl:copy>
  </xsl:template>
  <!-- The provider defaults ISO drives to IDE; Q35 requires SATA instead. -->
  <xsl:template match="disk[@device='cdrom']/target[@bus='ide']">
    <target bus="sata">
      <xsl:attribute name="dev">sd<xsl:number value="count(../preceding-sibling::disk[@device='cdrom']) + 1" format="a"/></xsl:attribute>
    </target>
  </xsl:template>
  <!-- Let libvirt allocate SATA addresses instead of retaining IDE addresses. -->
  <xsl:template match="disk[@device='cdrom'][target/@bus='ide']/address"/>
  <xsl:template match="controller[@type='ide']"/>
</xsl:stylesheet>
